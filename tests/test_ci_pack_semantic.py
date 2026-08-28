from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator

import pytest
import yaml

from scripts import ci_semantic_proof as SEMANTIC


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / ".github" / "ci" / "legacy-jobs.yml"
SPEC = importlib.util.spec_from_file_location(
    "run_ci_pack_semantic", ROOT / "scripts" / "run_ci_pack.py"
)
assert SPEC and SPEC.loader
PACK = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PACK
SPEC.loader.exec_module(PACK)

SHA_TREE = "1" * 40
SHA_HEAD = "2" * 40
SHA_BASE = "3" * 40


def _job(
    job_id: str,
    steps: list[dict[str, object]],
    *,
    ordinal: int = 0,
    timeout: int | None = 1,
) -> object:
    definition: dict[str, object] = {
        "if": PACK.DISABLED_IF,
        "runs-on": "ubuntu-latest",
        "steps": steps,
    }
    if timeout is not None:
        definition["timeout-minutes"] = timeout
    return PACK.LegacyJob(job_id, definition, ordinal, 1)


def _write_manifest(path: Path, jobs: list[object]) -> Path:
    payload = {
        "jobs": {
            job.job_id: job.definition
            for job in jobs
        }
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _plan(jobs: list[object], *, changed: list[str] | None = None) -> object:
    return PACK.build_plan(
        jobs,
        changed,
        changed_from=SHA_BASE if changed is not None else None,
        scope_mode="active",
        pack_count=max(1, len(jobs)),
        workflow_run_id="987654321",
        workflow="ci",
        event="pull_request",
        role="pr_head",
        tested_tree_sha=SHA_TREE,
        subject_head_sha=SHA_HEAD,
        base_sha=SHA_BASE,
    )


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _small_repository(path: Path) -> tuple[str, str]:
    path.mkdir()
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.email", "ci@example.test")
    _git(path, "config", "user.name", "CI Test")
    subject = path / "subject.txt"
    subject.write_text("base\n", encoding="utf-8")
    _git(path, "add", "subject.txt")
    _git(path, "commit", "-m", "base")
    base = _git(path, "rev-parse", "HEAD")
    subject.write_text("head\n", encoding="utf-8")
    _git(path, "commit", "-am", "head")
    return base, _git(path, "rev-parse", "HEAD")


def test_real_manifest_only_disambiguates_the_two_duplicate_sbir_steps() -> None:
    payload = yaml.safe_load(MANIFEST.read_text())
    explicit = [
        (job_id, step.get("name"), step["proof_id"])
        for job_id, definition in payload["jobs"].items()
        for step in definition.get("steps", [])
        if isinstance(step, dict) and "proof_id" in step
    ]
    assert explicit == [
        (
            "unrun-government-revenue",
            "SBIR/STTR progression evidence lane — collector + engine rail (#5012)",
            "sbir-sttr-progression-evidence-pre-amount-semantics",
        ),
        (
            "unrun-government-revenue",
            "SBIR/STTR progression evidence lane — collector + engine rail (#5012)",
            "sbir-sttr-progression-evidence-post-amount-semantics",
        ),
    ]


def test_real_manifest_plan_digest_is_shared_with_reconciler() -> None:
    """The exact production proof universe must cross the runner/core boundary."""
    jobs = PACK.load_legacy_jobs(MANIFEST)
    plan = PACK.build_plan(
        jobs,
        [".github/ci/legacy-jobs.yml"],
        changed_from=SHA_BASE,
        scope_mode="active",
        pack_count=12,
        workflow_run_id="987654321",
        workflow="ci",
        event="pull_request",
        role="pr_head",
        tested_tree_sha=SHA_TREE,
        subject_head_sha=SHA_HEAD,
        base_sha=SHA_BASE,
    )

    assert len(plan.semantic_jobs) == len(jobs)
    assert SEMANTIC.authoritative_plan_sha256(plan.to_dict()) == plan.plan_sha256
    # The production census migration is executable: all 614 semantic units now
    # have one non-empty identity unique inside their existing logical job.
    jobs = PACK.load_legacy_jobs(MANIFEST)
    semantic_count = sum(len(PACK.semantic_step_specs(job)) for job in jobs)
    assert semantic_count >= 614


def test_unnamed_and_duplicate_effective_proof_ids_fail_closed(
    tmp_path: Path,
) -> None:
    unnamed = _job("unnamed", [{"run": "true"}])
    path = _write_manifest(tmp_path / "unnamed.yml", [unnamed])
    with pytest.raises(PACK.ManifestError, match="invalid semantic identity"):
        PACK.load_legacy_jobs(path)

    duplicate = _job(
        "duplicate",
        [
            {"name": "same semantic proof", "run": "true"},
            {"name": "same semantic proof", "run": "true"},
        ],
    )
    path = _write_manifest(tmp_path / "duplicate.yml", [duplicate])
    with pytest.raises(PACK.ManifestError, match="not unique"):
        PACK.load_legacy_jobs(path)

    explicit = _job(
        "explicit",
        [
            {"name": "same semantic proof", "proof_id": "proof-a", "run": "true"},
            {"name": "same semantic proof", "proof_id": "proof-b", "run": "true"},
        ],
    )
    assert len(PACK.load_legacy_jobs(_write_manifest(tmp_path / "ok.yml", [explicit]))) == 1


def test_infrastructure_never_receives_a_semantic_identity(tmp_path: Path) -> None:
    job = _job(
        "demo",
        [
            {"uses": "actions/checkout@v4"},
            {"name": "install", "run": "python -m pip install pytest"},
            {"name": "proof", "run": "python -m pytest tests/test_demo.py -q"},
        ],
    )
    specs = PACK.semantic_step_specs(job)
    assert [spec.display_name for spec in specs] == ["proof"]

    job.definition["steps"][1]["proof_id"] = "not-semantic"
    path = _write_manifest(tmp_path / "bad.yml", [job])
    with pytest.raises(PACK.ManifestError, match="dependency infrastructure"):
        PACK.load_legacy_jobs(path)


def test_step_and_job_digests_separate_identity_from_execution_contract(
    tmp_path: Path,
) -> None:
    first = _job(
        "demo",
        [
            {"name": "old display", "proof_id": "stable-proof", "run": "echo ok"},
        ],
    )
    renamed = _job(
        "demo",
        [
            {"name": "new display", "proof_id": "stable-proof", "run": "echo ok"},
        ],
    )
    changed = _job(
        "demo",
        [
            {"name": "old display", "proof_id": "stable-proof", "run": "echo changed"},
        ],
    )
    assert PACK.semantic_step_specs(first)[0].proof_id == "stable-proof"
    assert (
        PACK.semantic_step_specs(first)[0].step_spec_sha256
        == PACK.semantic_step_specs(renamed)[0].step_spec_sha256
    )
    assert (
        PACK.semantic_step_specs(first)[0].step_spec_sha256
        != PACK.semantic_step_specs(changed)[0].step_spec_sha256
    )

    dependency_changed = _job(
        "demo",
        [
            {"name": "install", "run": "python -m pip install pytest==9"},
            {"name": "old display", "proof_id": "stable-proof", "run": "echo ok"},
        ],
    )
    assert PACK.semantic_job_digest(first) != PACK.semantic_job_digest(dependency_changed)

    default_checkout = _job(
        "demo",
        [
            {"uses": "actions/checkout@v4"},
            {"name": "old display", "proof_id": "stable-proof", "run": "echo ok"},
        ],
    )
    full_history = _job(
        "demo",
        [
            {"uses": "actions/checkout@v4", "with": {"fetch-depth": 0}},
            {"name": "old display", "proof_id": "stable-proof", "run": "echo ok"},
        ],
    )
    assert PACK.semantic_job_digest(default_checkout) != PACK.semantic_job_digest(
        full_history
    )

    unsupported = _job(
        "demo",
        [
            {"uses": "actions/checkout@v4", "with": {"fetch-depth": 2}},
            {"name": "proof", "run": "true"},
        ],
    )
    with pytest.raises(PACK.ManifestError, match="not provided by the pack runner"):
        PACK.load_legacy_jobs(
            _write_manifest(tmp_path / "unsupported-action.yml", [unsupported])
        )


def test_fetch_depth_zero_action_is_materialized_for_the_exact_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _job(
        "history",
        [
            {"uses": "actions/checkout@v4", "with": {"fetch-depth": 0}},
            {"name": "proof", "run": "true"},
        ],
    )
    calls: list[tuple[list[str], Path]] = []

    def run(command: list[str], *, cwd: Path, **_kwargs: object) -> object:
        calls.append((list(command), cwd))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(PACK, "_trusted_git_environment", lambda _root: {})
    monkeypatch.setattr(PACK.subprocess, "run", run)
    PACK._prepare_provided_actions(job, root=tmp_path, tested_tree_sha=SHA_TREE)
    assert calls == [
        (
            [
                "git",
                "fetch",
                "--no-recurse-submodules",
                "--prune",
                "--tags",
                "--depth=2147483647",
                "origin",
                "+refs/heads/*:refs/remotes/origin/*",
            ],
            tmp_path,
        )
    ]


def test_fetch_depth_zero_materializes_all_remote_branches_tags_and_history(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    base_sha, tested_sha = _small_repository(source)
    _git(source, "branch", "feature", base_sha)
    _git(source, "tag", "base-tag", base_sha)
    remote = tmp_path / "remote.git"
    subprocess.run(
        ["git", "clone", "--bare", str(source), str(remote)],
        check=True,
        capture_output=True,
    )
    checkout = tmp_path / "checkout"
    subprocess.run(
        [
            "git",
            "clone",
            "--depth=1",
            "--branch",
            "main",
            remote.as_uri(),
            str(checkout),
        ],
        check=True,
        capture_output=True,
    )
    job = _job(
        "history",
        [
            {"uses": "actions/checkout@v4", "with": {"fetch-depth": 0}},
            {"name": "proof", "run": "true"},
        ],
    )
    PACK._prepare_provided_actions(
        job,
        root=checkout,
        tested_tree_sha=tested_sha,
    )
    assert _git(checkout, "rev-parse", "origin/feature") == base_sha
    assert _git(checkout, "rev-parse", "base-tag") == base_sha
    assert int(_git(checkout, "rev-list", "--count", tested_sha)) == 2


def test_plan_v2_hash_binds_provenance_semantic_inventory_and_authority() -> None:
    job = _job("demo", [{"name": "proof", "run": "echo ok"}])
    plan = _plan([job], changed=["engine/example.py"])
    document = plan.to_dict()
    assert document["schema"] == "ci.pack_plan.v2"
    assert document["tested_tree_sha"] == SHA_TREE
    assert document["subject_head_sha"] == SHA_HEAD
    assert document["base_sha"] == SHA_BASE
    assert document["authority_changed"] is False
    assert document["semantic_jobs"] == [
        {
            "logical_job_id": "demo",
            "pack_index": 0,
            "job_exec_sha256": PACK.semantic_job_digest(job),
            "steps": [PACK.semantic_step_specs(job)[0].plan_dict()],
        }
    ]

    command_changed = _job("demo", [{"name": "proof", "run": "echo changed"}])
    assert _plan([command_changed], changed=["engine/example.py"]).plan_sha256 != plan.plan_sha256
    assert _plan([job], changed=["scripts/new_authority.py"]).authority_changed is True
    main = PACK.build_plan(
        [job],
        ["scripts/new_authority.py"],
        changed_from=None,
        scope_mode="active",
        pack_count=1,
        workflow_run_id="1",
        workflow="ci",
        event="workflow_dispatch",
        role="main",
        tested_tree_sha=SHA_TREE,
        subject_head_sha=SHA_TREE,
        base_sha=SHA_TREE,
    )
    assert main.authority_changed is False

    hash_payload = PACK.plan_hash_payload(
        workflow_run_id=plan.workflow_run_id,
        workflow=plan.workflow,
        event=plan.event,
        role=plan.role,
        tested_tree_sha=plan.tested_tree_sha,
        subject_head_sha=plan.subject_head_sha,
        base_sha=plan.base_sha,
        authority_changed=plan.authority_changed,
        changed_from=plan.changed_from,
        scope_mode=plan.scope_mode,
        changed_files_sha256=plan.changed_files_sha256,
        pack_count=plan.pack_count,
        eligible_job_ids=plan.eligible_job_ids,
        pack_jobs=plan.pack_jobs,
        pack_weights=plan.pack_weights,
        semantic_jobs=plan.semantic_jobs,
    )
    baseline = PACK._canonical_digest(hash_payload)
    mutations = {
        "tested_tree_sha": "a" * 40,
        "subject_head_sha": "b" * 40,
        "base_sha": "c" * 40,
        "changed_files_sha256": "d" * 64,
        "authority_changed": True,
    }
    for key, value in mutations.items():
        changed_payload = dict(hash_payload)
        changed_payload[key] = value
        assert PACK._canonical_digest(changed_payload) != baseline, key

    with pytest.raises(PACK.ManifestError, match="main semantic plan"):
        PACK.build_plan(
            [job],
            None,
            changed_from=SHA_BASE,
            scope_mode="active",
            event="workflow_dispatch",
            role="main",
            tested_tree_sha=SHA_TREE,
            subject_head_sha=SHA_TREE,
            base_sha=SHA_TREE,
        )
    with pytest.raises(PACK.ManifestError, match="changed_from must equal"):
        PACK.build_plan(
            [job],
            ["engine/example.py"],
            changed_from=SHA_BASE,
            scope_mode="active",
            event="pull_request",
            role="pr_head",
            tested_tree_sha=SHA_TREE,
            subject_head_sha=SHA_HEAD,
            base_sha="e" * 40,
        )


def test_pack_consumes_the_authoritative_plan_without_replanning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = _job("demo", [{"name": "proof", "run": "echo ok"}])
    manifest = _write_manifest(tmp_path / "manifest.yml", [job])
    loaded_job = PACK.load_legacy_jobs(manifest)[0]
    plan = _plan([loaded_job], changed=["engine/example.py"])
    plan_path = tmp_path / "plan" / "plan.json"
    PACK._atomic_write_json(plan_path, plan.to_dict(), indent=2)
    changed_path = tmp_path / "changed.json"
    changed_path.write_text('["engine/example.py"]\n', encoding="utf-8")

    monkeypatch.setattr(
        PACK,
        "infer_job_scopes",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("consumer must not replan")
        ),
    )
    consumed = PACK.load_authoritative_plan(
        plan_path,
        workflow=manifest,
        changed_files_file=changed_path,
        expect_plan_sha=plan.plan_sha256,
        expect_tested_tree_sha=SHA_TREE,
        expect_subject_head_sha=SHA_HEAD,
        expect_base_sha=SHA_BASE,
    )
    assert consumed == plan
    with pytest.raises(PACK.ManifestError, match="expected"):
        PACK.load_authoritative_plan(
            plan_path,
            workflow=manifest,
            changed_files_file=changed_path,
            expect_subject_head_sha="f" * 40,
        )

    duplicate = tmp_path / "duplicate-plan.json"
    duplicate.write_text(
        '{"schema":"ci.pack_plan.v2","schema":"ci.pack_plan.v2"}\n',
        encoding="utf-8",
    )
    with pytest.raises(PACK.ManifestError, match="duplicate key 'schema'"):
        PACK.load_authoritative_plan(duplicate, workflow=manifest)


def _canary_plan(jobs: list[object], *, changed: list[str] | None = None) -> object:
    """The one narrow diagnostic pair: pr_head/workflow_dispatch, admitted
    ONLY under the exact canary workflow name (#6351 P0R bridge, spec A).
    """
    return PACK.build_plan(
        jobs,
        changed,
        changed_from=SHA_BASE if changed is not None else None,
        scope_mode="active",
        pack_count=max(1, len(jobs)),
        workflow_run_id="987654321",
        workflow=PACK.DIAGNOSTIC_CANARY_WORKFLOW,
        event="workflow_dispatch",
        role="pr_head",
        tested_tree_sha=SHA_TREE,
        subject_head_sha=SHA_HEAD,
        base_sha=SHA_BASE,
    )


def test_load_authoritative_plan_admits_the_diagnostic_pair_only_for_its_exact_workflow_name(
    tmp_path: Path,
) -> None:
    """``load_authoritative_plan`` reads ``workflow`` BEFORE its role/event
    validation and grants the same narrow admission ``build_plan`` does — no
    other workflow name may pose as the diagnostic canary, and the refusal
    must fire on the role/event gate itself (before the digest check ever
    runs), not merely because a mutated document happens to hash differently.
    """
    job = _job("demo", [{"name": "proof", "run": "echo ok"}])
    manifest = _write_manifest(tmp_path / "manifest.yml", [job])
    loaded_job = PACK.load_legacy_jobs(manifest)[0]
    plan = _canary_plan([loaded_job], changed=["engine/example.py"])
    plan_path = tmp_path / "plan.json"
    PACK._atomic_write_json(plan_path, plan.to_dict(), indent=2)
    changed_path = tmp_path / "changed.json"
    changed_path.write_text('["engine/example.py"]\n', encoding="utf-8")

    consumed = PACK.load_authoritative_plan(
        plan_path,
        workflow=manifest,
        changed_files_file=changed_path,
        expect_plan_sha=plan.plan_sha256,
    )
    assert consumed.workflow == PACK.DIAGNOSTIC_CANARY_WORKFLOW
    assert consumed.role == "pr_head"
    assert consumed.event == "workflow_dispatch"

    document = json.loads(plan_path.read_text(encoding="utf-8"))
    for other_workflow in ("ci", "some-other-workflow"):
        mutated = dict(document, workflow=other_workflow)
        mutated_path = tmp_path / f"mutated-{other_workflow}.json"
        mutated_path.write_text(json.dumps(mutated), encoding="utf-8")
        with pytest.raises(PACK.ManifestError, match="unsupported"):
            PACK.load_authoritative_plan(
                mutated_path,
                workflow=manifest,
                changed_files_file=changed_path,
            )


def test_exact_empty_changed_list_round_trips_as_a_distinct_plan_input(
    tmp_path: Path,
) -> None:
    job = _job("demo", [{"name": "proof", "run": "echo ok"}])
    manifest = _write_manifest(tmp_path / "manifest.yml", [job])
    loaded_job = PACK.load_legacy_jobs(manifest)[0]
    plan = _plan([loaded_job], changed=[])
    assert plan.changed_paths == ()
    assert plan.changed_files_sha256 == PACK.changed_files_digest([])
    assert plan.changed_files_sha256

    plan_path = tmp_path / "plan.json"
    changed_path = tmp_path / "changed.json"
    PACK._atomic_write_json(plan_path, plan.to_dict())
    changed_path.write_text("[]\n", encoding="utf-8")
    consumed = PACK.load_authoritative_plan(
        plan_path,
        workflow=manifest,
        changed_files_file=changed_path,
        expect_plan_sha=plan.plan_sha256,
    )
    assert consumed.changed_paths == ()
    assert consumed.plan_sha256 == plan.plan_sha256


def test_runner_and_shared_reconciler_hash_unicode_plan_identically() -> None:
    """Production proof names are UTF-8; JSON escape style is not identity."""
    job = _job("unicode-proof", [{"name": "证明 receipt", "run": "echo ok"}])
    plan = _plan([job], changed=["engine/example.py"])

    assert SEMANTIC.authoritative_plan_sha256(plan.to_dict()) == plan.plan_sha256


def test_invalid_internal_job_result_blocks_infrastructure() -> None:
    job = _job("demo", [{"name": "proof", "run": "true"}])
    execution = PACK._coerce_job_execution(job, None)
    assert execution.infrastructure["outcome"] == "unknown"
    assert execution.steps[0]["outcome"] == "infrastructure_blocked"
    assert execution.failure is not None


def test_logical_job_deadline_yields_timeout_then_not_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _job(
        "demo",
        [
            {"name": "first", "run": "true"},
            {"name": "second", "run": "true"},
            {"name": "third", "run": "true"},
        ],
        timeout=1,
    )
    ticks = iter([100.0, 100.0, 161.0])
    monkeypatch.setattr(PACK.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(PACK, "_restore_workspace", lambda *_args: None)
    calls: list[float] = []

    def stream(*_args: object, timeout_seconds: float, **_kwargs: object) -> object:
        calls.append(timeout_seconds)
        return PACK.CommandObservation(outcome="passed", returncode=0)

    monkeypatch.setattr(PACK, "_stream_command", stream)
    result = PACK._run_job(job, base_ref="main", head_ref="feature", command_env={})
    assert calls == [60.0]
    assert [step["outcome"] for step in result.steps] == [
        "passed",
        "timed_out",
        "not_run_prior_failure",
    ]
    assert result.failure == "demo: timed out after 1 minutes"


def test_step_runner_exception_preserves_prior_pass_and_complete_accounting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _job(
        "demo",
        [
            {"name": "first", "run": "true"},
            {"name": "runner breaks", "run": "true"},
            {"name": "blocked later", "run": "true"},
        ],
    )
    monkeypatch.setattr(PACK, "_restore_workspace", lambda *_args: None)
    outcomes: Iterator[object] = iter(
        [
            PACK.CommandObservation(outcome="passed", returncode=0),
            RuntimeError("popen unavailable"),
        ]
    )

    def stream(*_args: object, **_kwargs: object) -> object:
        value = next(outcomes)
        if isinstance(value, BaseException):
            raise value
        return value

    monkeypatch.setattr(PACK, "_stream_command", stream)
    result = PACK._run_job(job, base_ref="main", head_ref="", command_env={})
    assert result.infrastructure["outcome"] == "unknown"
    assert [step["outcome"] for step in result.steps] == [
        "passed",
        "infrastructure_blocked",
        "infrastructure_blocked",
    ]


def test_dependency_failure_is_infrastructure_and_blocks_every_semantic_step(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    job = _job(
        "demo",
        [
            {"name": "install", "run": "python -m pip install pytest"},
            {"name": "first proof", "run": "false"},
            {"name": "second proof", "run": "false"},
        ],
    )
    fragment = tmp_path / "fragment.json"
    monkeypatch.setattr(PACK, "_workspace_root", lambda: tmp_path)
    monkeypatch.setattr(PACK, "_restore_workspace", lambda *_args: None)
    monkeypatch.setattr(
        PACK,
        "_dependency_environment",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("install exploded")
        ),
    )
    assert PACK.execute_pack([job], emit_semantic_fragment=fragment) == 1
    payload = json.loads(fragment.read_text())
    record = payload["jobs"][0]
    assert record["infrastructure"]["outcome"] == "dependency_failed"
    assert [step["outcome"] for step in record["steps"]] == [
        "infrastructure_blocked",
        "infrastructure_blocked",
    ]
    assert all(step["failure_signature"] is None for step in record["steps"])
    output = capsys.readouterr().out
    assert "::error title=legacy-job-demo::" in output
    assert json.loads(
        next(
            line.split("=", 1)[1]
            for line in output.splitlines()
            if line.startswith("CI_PACK_FAILED_JOBS=")
        )
    ) == ["demo"]


def test_dependency_environment_retries_exact_tls_record_once_in_a_fresh_venv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    observations = iter(
        [
            PACK.CommandObservation(
                outcome="failed",
                returncode=1,
                detail="exited 1",
                retryable_dependency_transport=True,
            ),
            PACK.CommandObservation(outcome="passed", returncode=0),
        ]
    )
    streamed: list[str] = []
    venv_creations: list[Path] = []

    def stream(command: str, **kwargs: object) -> object:
        streamed.append(command)
        assert kwargs["detect_retryable_dependency_transport"] is True
        return next(observations)

    def run(command: list[str], **_kwargs: object) -> object:
        assert command[:3] == [sys.executable, "-m", "venv"]
        target = Path(command[3])
        sentinel = target / "partial-install"
        if venv_creations:
            assert not sentinel.exists(), "retry inherited the partial first venv"
        target.mkdir(parents=True)
        sentinel.write_text("partial\n", encoding="utf-8")
        venv_creations.append(target)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(PACK, "_stream_command", stream)
    monkeypatch.setattr(PACK.subprocess, "run", run)

    environment = PACK._dependency_environment("python -m pip install plotly")

    assert streamed == [
        "python -m pip install plotly",
        "python -m pip install plotly",
    ]
    assert len(venv_creations) == 2
    assert venv_creations[0] == venv_creations[1]
    assert environment["PATH"].split(os.pathsep, 1)[0] == str(
        tmp_path / "ci-pack-job-env" / "bin"
    )
    output = capsys.readouterr().out
    assert "ci dependency transport retry" in output
    assert "recreating the isolated environment once" in output


def test_dependency_environment_does_not_retry_an_unclassified_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    streamed: list[str] = []

    def stream(command: str, **kwargs: object) -> object:
        streamed.append(command)
        assert kwargs["detect_retryable_dependency_transport"] is True
        return PACK.CommandObservation(
            outcome="failed",
            returncode=23,
            detail="exited 23",
        )

    monkeypatch.setattr(PACK, "_stream_command", stream)
    monkeypatch.setattr(
        PACK.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0),
    )

    with pytest.raises(RuntimeError, match="dependency install exited 23"):
        PACK._dependency_environment("python -m pip install plotly")
    assert streamed == ["python -m pip install plotly"]


def test_dependency_environment_fails_after_one_classified_tls_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    calls = 0

    def stream(_command: str, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        assert kwargs["detect_retryable_dependency_transport"] is True
        return PACK.CommandObservation(
            outcome="failed",
            returncode=1,
            detail="exited 1",
            retryable_dependency_transport=True,
        )

    monkeypatch.setattr(PACK, "_stream_command", stream)
    monkeypatch.setattr(
        PACK.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0),
    )

    with pytest.raises(RuntimeError, match="after one classified TLS retry"):
        PACK._dependency_environment("python -m pip install plotly")
    assert calls == 2


def test_dependency_environment_records_tls_retry_before_different_second_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    observations = iter(
        [
            PACK.CommandObservation(
                outcome="failed",
                returncode=1,
                detail="exited 1",
                retryable_dependency_transport=True,
            ),
            PACK.CommandObservation(
                outcome="failed",
                returncode=23,
                detail="exited 23",
            ),
        ]
    )
    monkeypatch.setattr(
        PACK,
        "_stream_command",
        lambda *_args, **_kwargs: next(observations),
    )
    monkeypatch.setattr(
        PACK.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0),
    )

    with pytest.raises(
        RuntimeError,
        match="dependency install exited 23 after one classified TLS retry",
    ):
        PACK._dependency_environment("python -m pip install plotly")


@pytest.mark.parametrize(
    "command",
    [
        "echo prepare; python -m pip install plotly",
        "python -m pip install plotly && echo replayed",
        "python -m pip install plotly; ./non_idempotent_step",
        "python -m pip install plotly | tee /tmp/output",
        "python -m pip install $(cat requirements.txt)",
        "python -m pip install `cat requirements.txt`",
    ],
)
def test_dependency_command_refuses_a_mixed_shell_body(command: str) -> None:
    job = _job(
        "mixed-install",
        [
            {
                "name": "not standalone",
                "run": command,
            },
            {"name": "proof", "run": "true"},
        ],
    )
    with pytest.raises(PACK.ManifestError, match="not a standalone pip command"):
        PACK.dependency_command(job)


def test_dependency_transport_marker_detection_crosses_stream_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunks = iter(
        [
            b"ssl.SSLError: [SSL: DECRYPTION_FAILED_OR_BAD_",
            b"RECORD_MAC] decryption failed or bad record mac\n",
            b"",
        ]
    )

    class Process:
        returncode = 1
        pid = 77
        stdout = SimpleNamespace(
            read=lambda _size: next(chunks),
            close=lambda: None,
        )

        def wait(self, timeout: object = None) -> int:
            return self.returncode

    monkeypatch.setattr(PACK.subprocess, "Popen", lambda *_args, **_kwargs: Process())
    observation = PACK._stream_command(
        "python -m pip install plotly",
        env={},
        timeout_seconds=None,
        detect_retryable_dependency_transport=True,
    )
    assert observation.outcome == "failed"
    assert observation.retryable_dependency_transport is True


@pytest.mark.parametrize(
    "near_miss",
    [
        b"ssl.SSLError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed\n",
        b"ssl.SSLError: [SSL: DECRYPTION_FAILED] decryption failed\n",
        b"ssl.SSLError: [SSL: DECRYPTION_FAILED_OR_BAD_RECORD] incomplete marker\n",
    ],
)
def test_dependency_transport_near_misses_are_not_retryable(
    monkeypatch: pytest.MonkeyPatch,
    near_miss: bytes,
) -> None:
    chunks = iter([near_miss, b""])

    class Process:
        returncode = 1
        pid = 77
        stdout = SimpleNamespace(
            read=lambda _size: next(chunks),
            close=lambda: None,
        )

        def wait(self, timeout: object = None) -> int:
            return self.returncode

    monkeypatch.setattr(PACK.subprocess, "Popen", lambda *_args, **_kwargs: Process())
    observation = PACK._stream_command(
        "python -m pip install plotly",
        env={},
        timeout_seconds=None,
        detect_retryable_dependency_transport=True,
    )
    assert observation.outcome == "failed"
    assert observation.retryable_dependency_transport is False


def test_explicit_changed_file_handle_overrides_stale_child_transports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale = tmp_path / "stale.json"
    authoritative = tmp_path / "authoritative.json"
    monkeypatch.setenv("CI_CHANGED_FILES_FILE", str(stale))
    monkeypatch.setenv("CI_CHANGED_FILES_JSON", '["stale.py"]')
    child = PACK._child_environment(authoritative)
    assert child["CI_CHANGED_FILES_FILE"] == str(authoritative)
    assert "CI_CHANGED_FILES_JSON" not in child


def test_child_environment_strips_repo_binding_git_vars(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GIT_DIR", "/foreign/repository/.git")
    monkeypatch.setenv("GIT_WORK_TREE", "/foreign/repository")
    monkeypatch.setenv("GIT_INDEX_FILE", "/foreign/repository/.git/index")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "keep-me")
    handle = tmp_path / "changed.json"
    handle.write_text("[]", encoding="utf-8")
    child = PACK._child_environment(handle)
    assert "GIT_DIR" not in child
    assert "GIT_WORK_TREE" not in child
    assert "GIT_INDEX_FILE" not in child
    assert child["GIT_AUTHOR_NAME"] == "keep-me"
    assert child["CI_CHANGED_FILES_FILE"] == str(handle)


def test_streaming_capture_retains_only_one_bounded_prefix_of_a_giant_line(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    collectors: list[object] = []

    class SpyCollector:
        def __init__(self, **limits: int) -> None:
            self.limits = limits
            self.feeds: list[bytes] = []
            collectors.append(self)

        def feed(self, value: str | bytes, *, truncated: bool = False) -> None:
            encoded = value if isinstance(value, bytes) else value.encode()
            self.feeds.append(encoded)

        def signature(self) -> None:
            return None

    monkeypatch.setattr(PACK, "FailureAtomCollector", SpyCollector)
    command = (
        f"{sys.executable} -c \"import sys; "
        "sys.stdout.write('x'*200000); sys.exit(7)\""
    )
    result = PACK._stream_command(
        command,
        env=os.environ,
        timeout_seconds=10,
    )
    capsys.readouterr()  # discard the deliberately streamed live payload
    collector = collectors[0]
    assert collector.limits == {
        "max_bytes": PACK.FAILURE_CAPTURE_MAX_BYTES,
        "max_atoms": PACK.FAILURE_CAPTURE_MAX_ATOMS,
        "max_line_bytes": PACK.FAILURE_CAPTURE_MAX_LINE_BYTES,
    }
    assert len(collector.feeds) == 1
    assert len(collector.feeds[0]) == PACK.FAILURE_CAPTURE_MAX_LINE_BYTES
    assert result.outcome == "failed"
    assert result.detail == "exited 7"
    assert "x" * 100 not in json.dumps(result.__dict__)


def test_streaming_capture_finds_a_late_failure_atom(
    capsys: pytest.CaptureFixture[str],
) -> None:
    script = (
        "import sys\n"
        "for index in range(2000): print(f'benign {index} ' + 'x' * 90)\n"
        "print('FAILED tests/test_demo.py::test_late - assertion changed')\n"
        "sys.exit(1)\n"
    )
    result = PACK._stream_command(
        f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}",
        env=os.environ,
        timeout_seconds=20,
    )
    capsys.readouterr()
    assert result.outcome == "failed"
    assert result.failure_signature is not None
    assert any(
        atom.startswith("pytest:failed:tests/test_demo.py::test_late")
        for atom in result.failure_signature["atoms"]
    )


def test_overlong_failure_atom_is_non_comparable_instead_of_prefix_colliding(
    capsys: pytest.CaptureFixture[str],
) -> None:
    signatures: list[object] = []
    for tail in ("HEAD_ASSERTION", "BASE_EXCEPTION"):
        summary = "FAILED tests/test_long.py::test_same - " + "A" * 5000 + tail
        script = f"import sys; print({summary!r}); sys.exit(1)"
        result = PACK._stream_command(
            f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}",
            env=os.environ,
            timeout_seconds=20,
        )
        signatures.append(result.failure_signature)
    capsys.readouterr()
    assert signatures == [None, None]


def test_exact_sha_acquisition_fetches_only_the_requested_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def git_run(args: list[str], **_kwargs: object) -> object:
        calls.append(list(args))
        if args[1:3] == ["cat-file", "-e"]:
            return SimpleNamespace(returncode=1, stdout="")
        if args[1] == "rev-parse":
            return SimpleNamespace(returncode=0, stdout=SHA_BASE + "\n")
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(PACK, "_git_run_bounded", git_run)
    assert PACK._ensure_exact_commit(tmp_path, SHA_BASE, deadline=999999999.0) == SHA_BASE
    fetch = next(command for command in calls if command[1] == "fetch")
    assert fetch == [
        "git",
        "fetch",
        "--no-tags",
        "--depth=1",
        "origin",
        SHA_BASE,
    ]
    assert all("--unshallow" not in command for command in calls)


def test_exact_base_checkout_pins_origin_main_even_after_source_advances(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    base_sha, head_sha = _small_repository(source)
    assert _git(source, "rev-parse", "main") == head_sha
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))

    with PACK._exact_base_worktree(
        source,
        base_sha,
        deadline=PACK.time.monotonic() + 30,
    ) as replay:
        assert _git(replay, "rev-parse", "HEAD") == base_sha
        assert _git(replay, "rev-parse", "origin/main") == base_sha
        _git(replay, "fetch", "origin", "main")
        assert _git(replay, "rev-parse", "origin/main") == base_sha
        assert Path(_git(replay, "rev-parse", "--git-dir")).resolve() != (
            source / ".git"
        ).resolve()


def _blobless_partial_clone(tmp_path: Path) -> tuple[Path, str, str]:
    """Build the runner's own checkout shape: a ``blob:none`` partial clone.

    ci.yml hands every pack ``filter: blob:none`` + ``fetch-depth: 1``, so the
    tree the replay borrows objects from is missing exactly the blobs the PR
    changed. Reproducing that needs a server that honours the filter — a bare
    repo without ``uploadpack.allowFilter`` answers "filtering not recognized
    by server, ignoring" and hands back a COMPLETE clone, which is how this
    trap hides from a test that looks correct.
    """
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", "-b", "main", str(origin))
    _git(origin, "config", "uploadpack.allowFilter", "true")
    _git(origin, "config", "uploadpack.allowAnySHA1InWant", "true")

    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-b", "main")
    _git(source, "config", "user.email", "ci@example.test")
    _git(source, "config", "user.name", "CI Test")
    (source / "changed.txt").write_text("base\n", encoding="utf-8")
    (source / "untouched.txt").write_text("shared\n", encoding="utf-8")
    _git(source, "add", "-A")
    _git(source, "commit", "-m", "base")
    base = _git(source, "rev-parse", "HEAD")
    (source / "changed.txt").write_text("head\n", encoding="utf-8")
    _git(source, "commit", "-am", "head")
    head = _git(source, "rev-parse", "HEAD")
    _git(source, "remote", "add", "origin", str(origin))
    _git(source, "push", "origin", "main")

    work = tmp_path / "work"
    _git(
        tmp_path,
        "clone",
        "--filter=blob:none",
        "--depth=1",
        "--no-local",
        origin.as_uri(),
        str(work),
    )
    # The base commit is not in a depth-1 checkout; acquiring it is exactly what
    # `_ensure_exact_commit` does, and it brings trees without blobs.
    _git(work, "fetch", "--no-tags", "--depth=1", "origin", base)
    return work, base, head


def _locally_missing_blobs(work: Path, sha: str) -> list[str]:
    oids = [
        line.split()[2]
        for line in _git(work, "ls-tree", "-r", sha).splitlines()
        if line.split()[1] == "blob"
    ]
    probe = subprocess.run(
        ["git", "cat-file", "--batch-check"],
        cwd=work,
        input="".join(f"{oid}\n" for oid in oids),
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_NO_LAZY_FETCH": "1"},
    )
    return [
        line.split(" ", 1)[0]
        for line in probe.stdout.splitlines()
        if line.endswith(" missing")
    ]


def test_base_replay_checks_out_a_base_sha_inside_a_partial_clone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A classifier that degrades to ``unknown`` reads as "probably your fault".

    Measured on PR #5853: `git checkout --detach --force <base>` inside the
    replay repository exited 1 on every pack, on every base, because alternates
    share OBJECTS but neither the partial-clone extension nor the promisor
    remote that could fetch the omitted ones. Every main-inherited red on the
    fleet was then reported `classification=unknown`, and `ship_loop_guard.py`
    charged it to the PR under the INTERNAL block ladder.
    """
    work, base, head = _blobless_partial_clone(tmp_path)

    # Guard the guard: if the fixture ever stops omitting blobs, this test is
    # vacuous and must say so rather than pass.
    missing = _locally_missing_blobs(work, base)
    assert missing, (
        "fixture is not a partial clone — no blob at the base commit is "
        "missing locally, so this test could not observe the defect"
    )

    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner-temp"))
    (tmp_path / "runner-temp").mkdir()
    with PACK._exact_base_worktree(
        work,
        base,
        deadline=PACK.time.monotonic() + 120,
    ) as replay:
        assert _git(replay, "rev-parse", "HEAD") == base
        # Content, not just the ref: a checkout that skipped unreadable blobs
        # still moves HEAD and still exits 1.
        assert (replay / "changed.txt").read_text(encoding="utf-8") == "base\n"
        assert (replay / "untouched.txt").read_text(encoding="utf-8") == "shared\n"
        assert _git(replay, "status", "--porcelain") == ""
    assert head != base


def test_base_replay_hydration_is_a_noop_without_a_promisor_remote(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A full checkout must not pay for, or trip over, partial-clone repair."""
    source = tmp_path / "source"
    base, _head = _small_repository(source)
    assert PACK._promisor_remote(source, deadline=PACK.time.monotonic() + 30) is None

    def _fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("hydration probed a repository with no promisor remote")

    monkeypatch.setattr(PACK, "_missing_tree_objects", _fail)
    PACK._hydrate_exact_base_objects(
        source, base, deadline=PACK.time.monotonic() + 30
    )


def test_a_failed_replay_command_reports_git_stderr_not_only_its_exit_status(
) -> None:
    """The exit status alone is why this stayed invisible for a whole fleet."""
    failure = subprocess.CalledProcessError(
        1,
        ["git", "checkout", "--detach", "--force", SHA_BASE],
        output="",
        stderr="error: unable to read sha1 file of data/x.json (deadbeef)\n",
    )
    detail = PACK._bounded_detail(failure)
    assert "returned non-zero exit status 1" in detail
    assert "unable to read sha1 file of data/x.json" in detail
    assert "\n" not in detail


def test_each_job_restores_and_verifies_the_immutable_tested_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    tested_sha, other_sha = _small_repository(source)
    _git(source, "checkout", "--detach", tested_sha)
    first = _job(
        "moves-head",
        [
            {"name": "move checkout", "run": f"git checkout --detach {other_sha}"},
            {"name": "must not run", "run": "true"},
        ],
        ordinal=0,
    )
    second = _job(
        "observes-bound-tree",
        [
            {
                "name": "exact tree proof",
                "run": f'test "$(git rev-parse HEAD)" = "{tested_sha}"',
            }
        ],
        ordinal=1,
    )
    plan = PACK.build_plan(
        [first, second],
        None,
        changed_from=None,
        scope_mode="active",
        pack_count=1,
        workflow_run_id="1",
        workflow="ci",
        event="workflow_dispatch",
        role="main",
        tested_tree_sha=tested_sha,
        subject_head_sha=tested_sha,
        base_sha=tested_sha,
    )
    fragment = tmp_path / "fragment.json"
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner-temp"))
    (tmp_path / "runner-temp").mkdir()
    monkeypatch.chdir(source)
    monkeypatch.setattr(PACK, "_workspace_root", lambda: source)
    assert (
        PACK.execute_pack(
            [first, second],
            plan=plan,
            emit_semantic_fragment=fragment,
            enable_base_replay=False,
        )
        == 1
    )
    payload = json.loads(fragment.read_text())
    by_job = {row["logical_job_id"]: row for row in payload["jobs"]}
    assert by_job["moves-head"]["infrastructure"]["outcome"] == "unknown"
    assert [step["outcome"] for step in by_job["moves-head"]["steps"]] == [
        "infrastructure_blocked",
        "infrastructure_blocked",
    ]
    assert by_job["observes-bound-tree"]["steps"][0]["outcome"] == "passed"
    assert _git(source, "rev-parse", "HEAD") == tested_sha


def test_git_replace_metadata_cannot_substitute_the_tested_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    tested_sha, replacement_sha = _small_repository(source)
    _git(source, "checkout", "--detach", tested_sha)
    job = _job(
        "replace-tree",
        [
            {
                "name": "plant replacement",
                "run": f"git replace {tested_sha} {replacement_sha}",
            },
            {"name": "must remain blocked", "run": "true"},
        ],
    )
    monkeypatch.chdir(source)
    result = PACK._run_job(
        job,
        base_ref="main",
        head_ref="",
        command_env=os.environ.copy(),
        tested_tree_sha=tested_sha,
    )
    assert result.infrastructure["outcome"] == "unknown"
    assert [step["outcome"] for step in result.steps] == [
        "infrastructure_blocked",
        "infrastructure_blocked",
    ]
    PACK._restore_workspace(tested_sha)
    assert _git(source, "for-each-ref", "--format=%(refname)", "refs/replace") == ""
    assert _git(source, "rev-parse", "HEAD") == tested_sha


def _stub_for_each_ref_128(monkeypatch: pytest.MonkeyPatch) -> None:
    real = PACK.subprocess.run

    def wrapped(args: object, **kwargs: object) -> object:
        argv = [str(part) for part in list(args)]  # type: ignore[arg-type]
        if len(argv) >= 2 and argv[0] == "git" and argv[1] == "for-each-ref":
            return subprocess.CompletedProcess(
                argv,
                128,
                stdout="",
                stderr="fatal: Unable to create packed-refs.lock: File exists\n",
            )
        return real(args, **kwargs)

    monkeypatch.setattr(PACK.subprocess, "run", wrapped)


def test_for_each_ref_128_without_replace_refs_is_not_infra_unknown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A racy replace-ref probe must not fail a job that did not rewrite history.

    Measured 2026-08-15 on PR #5750 pack-9: the 5-minute deadline SIGKILL'd
    pytest, then `git for-each-ref refs/replace` exited 128 and was reported
    as infrastructure unknown.
    """
    source = tmp_path / "source"
    tested_sha, _other = _small_repository(source)
    _git(source, "checkout", "--detach", tested_sha)
    _stub_for_each_ref_128(monkeypatch)
    job = _job("probe-128", [{"name": "ok", "run": "true"}])
    monkeypatch.chdir(source)
    result = PACK._run_job(
        job,
        base_ref="main",
        head_ref="",
        command_env=os.environ.copy(),
        tested_tree_sha=tested_sha,
    )
    assert result.failure is None
    assert result.infrastructure["outcome"] == "passed"
    assert [step["outcome"] for step in result.steps] == ["passed"]


def test_filesystem_replace_refs_still_block_when_for_each_ref_exits_128(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    tested_sha, replacement_sha = _small_repository(source)
    _git(source, "checkout", "--detach", tested_sha)
    _stub_for_each_ref_128(monkeypatch)
    job = _job(
        "replace-hidden",
        [
            {
                "name": "plant replacement",
                "run": f"git replace {tested_sha} {replacement_sha}",
            }
        ],
    )
    monkeypatch.chdir(source)
    result = PACK._run_job(
        job,
        base_ref="main",
        head_ref="",
        command_env=os.environ.copy(),
        tested_tree_sha=tested_sha,
    )
    assert result.infrastructure["outcome"] == "unknown"
    assert result.steps[0]["outcome"] == "infrastructure_blocked"
    assert "replace" in str(result.failure)


def test_timed_out_step_is_not_masked_by_rewrite_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    tested_sha, _other = _small_repository(source)
    _git(source, "checkout", "--detach", tested_sha)
    job = _job("slow", [{"name": "sleep", "run": "true"}])
    monkeypatch.chdir(source)

    def fake_stream(*_args: object, **_kwargs: object) -> object:
        return PACK.CommandObservation(
            outcome="timed_out",
            returncode=None,
            failure_signature=None,
            detail="semantic step exceeded its job timeout",
        )

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError(
            "Command '['git', 'for-each-ref', '--format=%(refname)', "
            "'refs/replace']' returned non-zero exit status 128."
        )

    monkeypatch.setattr(PACK, "_stream_command", fake_stream)
    monkeypatch.setattr(PACK, "_assert_no_git_rewrites", boom)
    result = PACK._run_job(
        job,
        base_ref="main",
        head_ref="",
        command_env=os.environ.copy(),
        tested_tree_sha=tested_sha,
    )
    assert result.failure is not None
    assert "timed out" in result.failure
    assert "infrastructure unknown" not in result.failure
    assert [step["outcome"] for step in result.steps] == ["timed_out"]


def test_trusted_git_environment_disables_optional_locks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    _small_repository(source)
    monkeypatch.setenv("GIT_DIR", "/foreign/repository/.git")
    monkeypatch.setenv("GIT_WORK_TREE", "/foreign/repository")
    env = PACK._trusted_git_environment(source)
    assert env["GIT_OPTIONAL_LOCKS"] == "0"
    assert env["GIT_NO_REPLACE_OBJECTS"] == "1"
    assert "GIT_DIR" not in env
    assert "GIT_WORK_TREE" not in env


def test_rewrite_probe_uses_checkout_path_not_foreign_git_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    tested_sha, _other = _small_repository(source)
    _git(source, "checkout", "--detach", tested_sha)
    monkeypatch.setenv("GIT_DIR", "/foreign/repository/.git")
    monkeypatch.setenv("GIT_WORK_TREE", "/foreign/repository")
    PACK._assert_no_git_rewrites(source)
    assert PACK._current_commit_sha(source) == tested_sha


def test_job_steps_must_not_inherit_checkout_git_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nested `git init` must not operate on the pack checkout.

    Measured 2026-08-15 on PR #5750: GIT_DIR/GIT_WORK_TREE in the job env
    made tmp_path inits hit the CI tree (exit 128), a sparse cone hid
    tests/*.py (pytest usage exit 4), and rev-parse HEAD then failed as
    infrastructure unknown.
    """
    source = tmp_path / "source"
    tested_sha, _other = _small_repository(source)
    _git(source, "checkout", "--detach", tested_sha)
    nested = tmp_path / "nested-work"
    job = _job(
        "nested-git",
        [
            {
                "name": "init a throwaway repo",
                "run": (
                    f"mkdir -p {shlex.quote(str(nested))} && "
                    f"git init -q -b main {shlex.quote(str(nested))} && "
                    f"git -C {shlex.quote(str(nested))} config user.email t@t && "
                    f"git -C {shlex.quote(str(nested))} config user.name t && "
                    f"git -C {shlex.quote(str(nested))} commit --allow-empty -qm seed"
                ),
            }
        ],
    )
    monkeypatch.chdir(source)
    captured: list[dict[str, str]] = []
    real_stream = PACK._stream_command

    def stream(
        command: str,
        *,
        env: dict[str, str],
        timeout_seconds: float | None = None,
    ) -> object:
        captured.append(dict(env))
        return real_stream(command, env=env, timeout_seconds=timeout_seconds)

    monkeypatch.setattr(PACK, "_stream_command", stream)
    planted = os.environ.copy()
    planted["GIT_DIR"] = str(source / ".git")
    planted["GIT_WORK_TREE"] = str(source)
    result = PACK._run_job(
        job,
        base_ref="main",
        head_ref="",
        command_env=planted,
        tested_tree_sha=tested_sha,
    )
    assert result.failure is None
    assert [step["outcome"] for step in result.steps] == ["passed"]
    assert captured
    assert "GIT_DIR" not in captured[0]
    assert "GIT_WORK_TREE" not in captured[0]
    assert captured[0].get("GIT_NO_REPLACE_OBJECTS") == "1"
    assert (nested / ".git").exists()
    assert _git(nested, "rev-parse", "--is-inside-work-tree") == "true"
    assert _git(source, "rev-parse", "HEAD") == tested_sha


def test_restore_workspace_reopens_a_sparse_cone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    _small_repository(source)
    keep = source / "keep" / "nested"
    skip = source / "skip" / "nested"
    keep.mkdir(parents=True)
    skip.mkdir(parents=True)
    (keep / "a.txt").write_text("keep\n", encoding="utf-8")
    (skip / "b.txt").write_text("skip\n", encoding="utf-8")
    _git(source, "add", "keep", "skip")
    _git(source, "commit", "-m", "nested")
    tested_sha = _git(source, "rev-parse", "HEAD")
    _git(source, "checkout", "--detach", tested_sha)
    _git(source, "sparse-checkout", "init", "--cone")
    _git(source, "sparse-checkout", "set", "--cone", "--", "keep")
    assert not (skip / "b.txt").exists()
    assert (keep / "a.txt").exists()
    monkeypatch.chdir(source)
    PACK._restore_workspace(tested_sha)
    assert _git(source, "rev-parse", "HEAD") == tested_sha
    assert (skip / "b.txt").read_text(encoding="utf-8") == "skip\n"


def _assert_pack_git_boundary(source: Path, tested_sha: str) -> None:
    assert _git(source, "for-each-ref", "--format=%(refname)", "refs/replace") == ""
    assert _git(source, "rev-parse", "HEAD") == tested_sha


def test_restore_workspace_heals_corrupt_packed_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    tested_sha, _other = _small_repository(source)
    _git(source, "checkout", "--detach", tested_sha)
    (source / ".git" / "packed-refs").write_text("not-valid\n", encoding="utf-8")
    with pytest.raises(subprocess.CalledProcessError):
        _git(source, "for-each-ref", "--format=%(refname)", "refs/replace")
    monkeypatch.chdir(source)
    PACK._restore_workspace(tested_sha)
    _assert_pack_git_boundary(source, tested_sha)
    assert (source / "subject.txt").read_text(encoding="utf-8") == "base\n"


def test_restore_workspace_heals_missing_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    tested_sha, _other = _small_repository(source)
    _git(source, "checkout", "--detach", tested_sha)
    (source / ".git" / "HEAD").unlink()
    monkeypatch.chdir(source)
    PACK._restore_workspace(tested_sha)
    _assert_pack_git_boundary(source, tested_sha)


def test_passed_step_that_breaks_packed_refs_leaves_probes_working(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    tested_sha, _other = _small_repository(source)
    _git(source, "checkout", "--detach", tested_sha)
    job = _job(
        "smash-refs",
        [{"name": "corrupt packed-refs", "run": "printf 'not-valid\\n' > .git/packed-refs"}],
    )
    monkeypatch.chdir(source)
    result = PACK._run_job(
        job,
        base_ref="main",
        head_ref="",
        command_env=os.environ.copy(),
        tested_tree_sha=tested_sha,
    )
    assert result.infrastructure["outcome"] == "unknown"
    assert [step["outcome"] for step in result.steps] == ["infrastructure_blocked"]
    _assert_pack_git_boundary(source, tested_sha)


def test_timeout_after_broken_git_stays_timeout_and_leaves_probes_working(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    tested_sha, _other = _small_repository(source)
    _git(source, "checkout", "--detach", tested_sha)
    job = _job(
        "timeout-smash",
        [{"name": "killed mid-step", "run": "true"}],
    )

    def stream(
        command: str,
        *,
        env: dict[str, str],
        timeout_seconds: float | None = None,
    ) -> object:
        (source / ".git" / "packed-refs").write_text("not-valid\n", encoding="utf-8")
        return PACK.CommandObservation(
            outcome="timed_out",
            returncode=None,
            failure_signature=None,
            detail="semantic step exceeded its job timeout",
        )

    monkeypatch.chdir(source)
    monkeypatch.setattr(PACK, "_stream_command", stream)
    result = PACK._run_job(
        job,
        base_ref="main",
        head_ref="",
        command_env=os.environ.copy(),
        tested_tree_sha=tested_sha,
    )
    assert result.infrastructure["outcome"] == "passed"
    assert result.failure == "timeout-smash: timed out after 1 minutes"
    assert [step["outcome"] for step in result.steps] == ["timed_out"]
    _assert_pack_git_boundary(source, tested_sha)


def test_base_replay_uses_base_runner_and_is_serial_without_matrix_fanout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for capability in (
        "GITHUB_TOKEN",
        "GH_TOKEN",
        "ACTIONS_RUNTIME_TOKEN",
        "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
        "ACTIONS_ID_TOKEN_REQUEST_URL",
        "ACTIONS_CACHE_URL",
        "ACTIONS_RESULTS_URL",
    ):
        monkeypatch.setenv(capability, "must-not-reach-base")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/candidate/controlled/library/path")
    monkeypatch.setattr(
        PACK,
        "_selected_python_loader_environment",
        lambda: {"LD_LIBRARY_PATH": "/trusted/python-3.12.13/lib"},
    )
    jobs = [
        _job("alpha", [{"name": "proof alpha", "run": "false"}], ordinal=0),
        _job("beta", [{"name": "proof beta", "run": "false"}], ordinal=1),
    ]
    plan = _plan(jobs, changed=["engine/example.py"])
    base_root = tmp_path / "exact-base-worktree"
    (base_root / "scripts").mkdir(parents=True)
    (base_root / ".github" / "ci").mkdir(parents=True)
    (base_root / "scripts" / "run_ci_pack.py").write_text("# base runner\n")
    (base_root / ".github" / "ci" / "legacy-jobs.yml").write_text("jobs: {}\n")

    @contextlib.contextmanager
    def base_worktree(*_args: object, **_kwargs: object) -> Iterator[Path]:
        yield base_root

    monkeypatch.setattr(PACK, "_exact_base_worktree", base_worktree)
    calls: list[tuple[list[str], Path, dict[str, str]]] = []
    active = 0
    max_active = 0

    def stream(
        command: list[str], *, cwd: Path, env: dict[str, str], deadline: float
    ) -> tuple[int, bool]:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        job_id = command[command.index("--semantic-replay-job") + 1]
        output = Path(command[command.index("--emit-semantic-fragment") + 1])
        calls.append((list(command), cwd, dict(env)))
        output.write_text(
            json.dumps(
                {
                    "schema": PACK.FRAGMENT_SCHEMA,
                    "tested_tree_sha": SHA_BASE,
                    "subject_head_sha": SHA_BASE,
                    "base_sha": SHA_BASE,
                    "role": "main",
                    "jobs": [
                        {
                            "logical_job_id": job_id,
                            "job_exec_sha256": "a" * 64,
                            "infrastructure": {"outcome": "passed"},
                            "steps": [
                                {
                                    "proof_id": f"proof-{job_id}",
                                    "step_spec_sha256": "b" * 64,
                                    "outcome": "passed",
                                    "failure_signature": None,
                                }
                            ],
                        }
                    ],
                }
            )
        )
        active -= 1
        return 0, False

    monkeypatch.setattr(PACK, "_stream_process_with_deadline", stream)
    records = [
        {
            "logical_job_id": job.job_id,
            "job_exec_sha256": PACK.semantic_job_digest(job),
            "infrastructure": {"outcome": "passed"},
            "steps": [
                {
                    **PACK.semantic_step_specs(job)[0].plan_dict(),
                    "outcome": "failed",
                    "failure_signature": {"sha256": "c" * 64, "atoms": ["x"]},
                }
            ],
        }
        for job in jobs
    ]
    PACK._run_exact_base_replays(
        root=tmp_path,
        plan=plan,
        records=records,
        budget_seconds=60,
    )
    assert max_active == 1
    assert len(calls) == 2
    for command, cwd, env in calls:
        assert command[1] == str(base_root / "scripts" / "run_ci_pack.py")
        assert cwd == base_root
        assert env["GITHUB_WORKSPACE"] == str(base_root)
        assert env["CI_BASE_REF"] == "main"
        assert env["CI_HEAD_REF"] == "main"
        assert env["LD_LIBRARY_PATH"] == "/trusted/python-3.12.13/lib"
        assert Path(env["CI_CHANGED_FILES_FILE"]).read_text() == "null\n"
        assert not any(
            value == "must-not-reach-base" for value in env.values()
        )
        assert "--pack-index" not in command
        assert "--pack-count" not in command
        assert "--semantic-replay-job" in command
    assert all(
        step["base_replay"]["tested_tree_sha"] == SHA_BASE
        for record in records
        for step in record["steps"]
    )
    assert all(
        step["base_replay"]["job_present"] is True
        for record in records
        for step in record["steps"]
    )


def test_selected_python_loader_environment_is_derived_from_the_interpreter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prefix = tmp_path / "python-3.12.13"
    library_dir = prefix / "lib"
    library_dir.mkdir(parents=True)
    (library_dir / "libpython3.12.so.1.0").write_bytes(b"fixture")
    monkeypatch.setattr(PACK.platform, "system", lambda: "Linux")
    monkeypatch.setattr(PACK.sys, "base_prefix", str(prefix))
    monkeypatch.setattr(
        PACK.sysconfig,
        "get_config_var",
        lambda name: {
            "LIBDIR": str(library_dir),
            "LDLIBRARY": "libpython3.12.so.1.0",
        }.get(name),
    )
    monkeypatch.setenv("LD_LIBRARY_PATH", "/candidate/controlled/library/path")

    assert PACK._selected_python_loader_environment() == {
        "LD_LIBRARY_PATH": str(library_dir.resolve())
    }


def test_selected_python_loader_environment_preserves_the_attested_tool_cache_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prefix = tmp_path / "hostedtoolcache" / "Python" / "3.12.13" / "x64"
    library_dir = prefix / "lib"
    library_dir.mkdir(parents=True)
    (library_dir / "libpython3.12.so.1.0").write_bytes(b"fixture")
    tool_cache_alias = (
        tmp_path / "runner" / "_work" / "_tool" / "Python" / "3.12.13" / "x64"
    )
    tool_cache_alias.parent.mkdir(parents=True)
    tool_cache_alias.symlink_to(prefix, target_is_directory=True)
    ambient_library_dir = tool_cache_alias / "lib"
    monkeypatch.setattr(PACK.platform, "system", lambda: "Linux")
    monkeypatch.setattr(PACK.sys, "base_prefix", str(prefix))
    monkeypatch.setattr(
        PACK.sysconfig,
        "get_config_var",
        lambda name: {
            "LIBDIR": str(library_dir),
            "LDLIBRARY": "libpython3.12.so",
            "INSTSONAME": "libpython3.12.so.1.0",
        }.get(name),
    )
    monkeypatch.setenv("LD_LIBRARY_PATH", str(ambient_library_dir))

    assert PACK._selected_python_loader_environment() == {
        "LD_LIBRARY_PATH": str(ambient_library_dir)
    }


def test_selected_python_loader_environment_refuses_a_library_outside_the_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prefix = tmp_path / "python-3.12.13"
    prefix.mkdir()
    outside = tmp_path / "candidate-library"
    outside.mkdir()
    (outside / "libpython3.12.so.1.0").write_bytes(b"fixture")
    monkeypatch.setattr(PACK.platform, "system", lambda: "Linux")
    monkeypatch.setattr(PACK.sys, "base_prefix", str(prefix))
    monkeypatch.setattr(
        PACK.sysconfig,
        "get_config_var",
        lambda name: {
            "LIBDIR": str(outside),
            "LDLIBRARY": "libpython3.12.so.1.0",
        }.get(name),
    )

    with pytest.raises(PACK.ExecutionProfileError, match="outside selected interpreter"):
        PACK._selected_python_loader_environment()


@pytest.mark.parametrize(
    ("library_dir", "library_name", "message"),
    [
        (None, "libpython3.12.so.1.0", "does not declare LIBDIR"),
        ("inside", None, "does not declare LDLIBRARY"),
        ("inside", "libpython3.12.so.1.0", "shared library is absent"),
    ],
)
def test_selected_python_loader_environment_refuses_missing_library_metadata_or_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    library_dir: str | None,
    library_name: str | None,
    message: str,
) -> None:
    prefix = tmp_path / "python-3.12.13"
    prefix.mkdir()
    declared_dir = prefix / "lib"
    declared_dir.mkdir()
    monkeypatch.setattr(PACK.platform, "system", lambda: "Linux")
    monkeypatch.setattr(PACK.sys, "base_prefix", str(prefix))
    monkeypatch.setattr(
        PACK.sysconfig,
        "get_config_var",
        lambda name: {
            "LIBDIR": str(declared_dir) if library_dir == "inside" else library_dir,
            "LDLIBRARY": library_name,
        }.get(name),
    )

    with pytest.raises(PACK.ExecutionProfileError, match=message):
        PACK._selected_python_loader_environment()


def test_replay_process_never_invents_time_after_the_shared_deadline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    waits: list[float] = []

    class Process:
        pid = 123
        returncode: int | None = None

        def wait(self, *, timeout: float) -> int:
            waits.append(timeout)
            if len(waits) == 1:
                raise subprocess.TimeoutExpired(["base-runner"], timeout)
            self.returncode = -9
            return self.returncode

    ticks = iter([0.0, 2.0, 10.0])
    monkeypatch.setattr(PACK.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(PACK.subprocess, "Popen", lambda *_args, **_kwargs: Process())
    monkeypatch.setattr(PACK.os, "killpg", lambda *_args: None)
    returncode, timed_out = PACK._stream_process_with_deadline(
        ["base-runner"],
        cwd=tmp_path,
        env={},
        deadline=10.0,
    )
    assert timed_out is True
    assert returncode == -9
    assert waits == [8.0, 0.0]


def test_replay_cleanup_does_not_extend_an_exhausted_deadline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = PACK.threading.Event()
    release = PACK.threading.Event()

    def slow_cleanup(*_args: object, **_kwargs: object) -> None:
        started.set()
        release.wait(timeout=5)

    monkeypatch.setattr(PACK.shutil, "rmtree", slow_cleanup)
    before = PACK.time.monotonic()
    PACK._bounded_rmtree(tmp_path / "replay", deadline=before - 1)
    elapsed = PACK.time.monotonic() - before
    assert started.wait(timeout=0.2)
    assert elapsed < 0.2
    release.set()


def test_fragment_is_bound_to_exact_plan_tree_head_base_and_accounts_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = _job(
        "demo",
        [
            {"name": "first", "run": "true"},
            {"name": "second", "run": "true"},
        ],
    )
    plan = _plan([job], changed=["engine/example.py"])
    fragment = tmp_path / "nested" / "fragment.json"
    monkeypatch.setattr(PACK, "_workspace_root", lambda: tmp_path)
    monkeypatch.setattr(PACK, "_current_commit_sha", lambda _root: SHA_TREE)
    monkeypatch.setattr(PACK, "_restore_workspace", lambda *_args: None)
    monkeypatch.setattr(
        PACK,
        "_dependency_environment",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(PACK, "_run_exact_base_replays", lambda **_kwargs: None)
    assert (
        PACK.execute_pack(
            [job],
            plan=plan,
            pack_index=0,
            emit_semantic_fragment=fragment,
        )
        == 0
    )
    payload = json.loads(fragment.read_text())
    assert payload["schema"] == PACK.FRAGMENT_SCHEMA
    assert set(payload) == {
        "schema",
        "workflow_run_id",
        "workflow",
        "event",
        "role",
        "tested_tree_sha",
        "subject_head_sha",
        "base_sha",
        "plan_sha256",
        "pack_index",
        "infrastructure",
        "jobs",
    }
    assert payload["plan_sha256"] == plan.plan_sha256
    assert payload["tested_tree_sha"] == SHA_TREE
    assert payload["subject_head_sha"] == SHA_HEAD
    assert payload["base_sha"] == SHA_BASE
    rows = payload["jobs"][0]["steps"]
    assert set(payload["jobs"][0]) == {
        "logical_job_id",
        "job_exec_sha256",
        "infrastructure",
        "steps",
    }
    assert all(
        set(row)
        == {
            "proof_id",
            "step_spec_sha256",
            "outcome",
            "failure_signature",
        }
        for row in rows
    )
    assert [(row["proof_id"], row["outcome"]) for row in rows] == [
        (spec.proof_id, "passed") for spec in PACK.semantic_step_specs(job)
    ]
    assert all("classification" not in row for row in rows)

    # The pack emits raw transport facts only. The shared authority consumes
    # that exact fragment and is solely responsible for the clear verdict.
    evidence = SEMANTIC.reconcile_evidence(plan.to_dict(), [payload])
    assert evidence["status"] == "clear"
    assert SEMANTIC.semantic_gate_verdict(evidence).clear is True
    assert [step["classification"] for step in evidence["jobs"][0]["steps"]] == [
        "passed",
        "passed",
    ]


def test_wrong_checkout_emits_runner_startup_blocked_fragment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = _job("demo", [{"name": "proof", "run": "true"}])
    plan = _plan([job], changed=["engine/example.py"])
    fragment = tmp_path / "blocked.json"
    monkeypatch.setattr(PACK, "_workspace_root", lambda: tmp_path)
    monkeypatch.setattr(PACK, "_current_commit_sha", lambda _root: "f" * 40)
    monkeypatch.setattr(
        PACK,
        "_run_job",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("wrong checkout must execute nothing")
        ),
    )
    assert (
        PACK.execute_pack(
            [job],
            plan=plan,
            pack_index=0,
            emit_semantic_fragment=fragment,
        )
        == 1
    )
    payload = json.loads(fragment.read_text())
    assert payload["tested_tree_sha"] == SHA_TREE
    assert payload["infrastructure"][0]["outcome"] == "runner_startup_failed"
    assert payload["jobs"][0]["infrastructure"]["outcome"] == (
        "runner_startup_failed"
    )
    assert payload["jobs"][0]["steps"][0]["outcome"] == (
        "infrastructure_blocked"
    )
