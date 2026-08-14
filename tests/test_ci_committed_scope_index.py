from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import ci_committed_scope_index as scope_index
from scripts import ci_structural_preflight as structural_preflight
from scripts import run_ci_pack as ci_pack


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_scope_index_binds_every_authoritative_planner_selector_source() -> None:
    assert tuple(path.as_posix() for path in scope_index.SELECTOR_SOURCES) == (
        ci_pack.PLAN_SELECTOR_INPUTS
    )


@pytest.fixture
def tiny_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    manifest = root / ".github/ci/legacy-jobs.yml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        """\
jobs:
  alpha:
    if: ${{ false }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python -c 'print("alpha")'
  beta:
    if: ${{ false }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python -c 'print("beta")'
""",
        encoding="utf-8",
    )
    workflow = root / ".github/workflows/ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "on:\n"
        "  pull_request: {}\n"
        "jobs:\n"
        "  ci-plan:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: echo plan\n"
        "  ci-pack:\n"
        "    needs: ci-plan\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: echo pack\n"
        "  ci-gate:\n"
        "    needs: [ci-plan, ci-pack]\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: echo gate\n",
        encoding="utf-8",
    )
    for relative in scope_index.SELECTOR_SOURCES:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPO_ROOT / relative).read_bytes())
    (root / "engine").mkdir()
    (root / "engine" / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "engine" / "worker.py").write_text(
        "def calculate():\n    return 1\n", encoding="utf-8"
    )
    return root


def _fixture_inference(jobs: list[ci_pack.LegacyJob]):
    return (
        [
            replace(
                jobs[0],
                # Deliberately unordered: generation owns canonical ordering.
                paths=("tests/test_alpha.py", "engine/**"),
            ),
            replace(jobs[1], paths=("browser/momoedge_capture/",)),
        ],
        "tiny fixture",
    )


def _generate(tiny_repo: Path, name: str = "scope-index.json") -> Path:
    output = tiny_repo.parent / name
    scope_index.generate_scope_index(
        output_path=output,
        repo_root=tiny_repo,
        pack_module=ci_pack,
        infer_scopes=_fixture_inference,
    )
    return output


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_and_reseal(path: Path, payload: dict) -> None:
    core = {key: value for key, value in payload.items() if key != "index_sha256"}
    canonical = json.dumps(
        core,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    payload["index_sha256"] = hashlib.sha256(canonical).hexdigest()
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_generation_is_deterministic_and_load_returns_legacy_job_replacements(
    tiny_repo: Path,
) -> None:
    first = _generate(tiny_repo, "first.json")
    second = _generate(tiny_repo, "second.json")

    assert first.read_bytes() == second.read_bytes()
    receipt = scope_index.verify_scope_index(
        first,
        repo_root=tiny_repo,
        pack_module=ci_pack,
    )
    live_jobs = ci_pack.load_legacy_jobs(
        tiny_repo / ".github/ci/legacy-jobs.yml"
    )

    assert receipt.elapsed_seconds < 1.0
    assert receipt.dependency_signature_count == len(
        list(tiny_repo.rglob("*.py"))
    )
    assert all(isinstance(job, ci_pack.LegacyJob) for job in receipt.jobs)
    assert [job.definition for job in receipt.jobs] == [
        job.definition for job in live_jobs
    ]
    assert [
        (job.job_id, job.ordinal, job.weight, job.paths) for job in receipt.jobs
    ] == [
        ("alpha", live_jobs[0].ordinal, live_jobs[0].weight, ("engine/**", "tests/test_alpha.py")),
        ("beta", live_jobs[1].ordinal, live_jobs[1].weight, ("browser/momoedge_capture/",)),
    ]
    assert scope_index.load_scope_index(
        first,
        repo_root=tiny_repo,
        pack_module=ci_pack,
    ) == list(receipt.jobs)


def test_cli_generate_and_verify(tiny_repo: Path, capsys: pytest.CaptureFixture) -> None:
    output = tiny_repo.parent / "cli-index.json"
    assert (
        scope_index.main(
            [
                "generate",
                "--repo-root",
                str(tiny_repo),
                "--output",
                str(output),
            ],
            pack_module=ci_pack,
            infer_scopes=_fixture_inference,
        )
        == 0
    )
    assert "SCOPE_INDEX_GENERATED=" in capsys.readouterr().out

    no_inference = SimpleNamespace(
        load_legacy_jobs=ci_pack.load_legacy_jobs,
        infer_job_scopes=lambda _jobs: pytest.fail("verify must not infer scopes"),
    )
    assert (
        scope_index.main(
            [
                "verify",
                "--repo-root",
                str(tiny_repo),
                "--index",
                str(output),
            ],
            pack_module=no_inference,
        )
        == 0
    )
    assert "SCOPE_INDEX_VERIFIED=" in capsys.readouterr().out


def test_digest_tamper_fails_closed(tiny_repo: Path) -> None:
    index = _generate(tiny_repo)
    payload = _read(index)
    payload["jobs"][0]["paths"][0] = "engine/tampered.py"
    index.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(scope_index.ScopeIndexError, match="digest mismatch"):
        scope_index.load_scope_index(
            index,
            repo_root=tiny_repo,
            pack_module=ci_pack,
        )


def test_manifest_hash_drift_fails_before_manifest_load(tiny_repo: Path) -> None:
    index = _generate(tiny_repo)
    manifest = tiny_repo / ".github/ci/legacy-jobs.yml"
    manifest.write_text(manifest.read_text(encoding="utf-8") + "# drift\n")

    with pytest.raises(scope_index.ScopeIndexError, match="manifest hash drift"):
        scope_index.load_scope_index(
            index,
            repo_root=tiny_repo,
            pack_module=ci_pack,
        )


@pytest.mark.parametrize("selector", scope_index.SELECTOR_SOURCES)
def test_each_selector_source_hash_is_bound(
    tiny_repo: Path,
    selector: Path,
) -> None:
    index = _generate(tiny_repo)
    source = tiny_repo / selector
    source.write_bytes(source.read_bytes() + b"\n# drift\n")

    with pytest.raises(scope_index.ScopeIndexError, match="selector source hash drift"):
        scope_index.load_scope_index(
            index,
            repo_root=tiny_repo,
            pack_module=ci_pack,
        )


def test_selector_source_inventory_and_order_are_exact(tiny_repo: Path) -> None:
    index = _generate(tiny_repo)
    payload = _read(index)
    payload["selector_sources"].reverse()
    _write_and_reseal(index, payload)

    with pytest.raises(scope_index.ScopeIndexError, match="inventory/order mismatch"):
        scope_index.load_scope_index(
            index,
            repo_root=tiny_repo,
            pack_module=ci_pack,
        )


def test_dependency_signature_inventory_is_digest_bound(tiny_repo: Path) -> None:
    index = _generate(tiny_repo)
    payload = _read(index)
    payload["dependency_signatures"]["files"][0]["signature_sha256"] = "0" * 64
    index.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(scope_index.ScopeIndexError, match="digest mismatch"):
        scope_index.load_dependency_signature_inventory(index)


def test_body_only_python_edit_keeps_dependency_signature_current(
    tiny_repo: Path,
) -> None:
    index = _generate(tiny_repo)
    inventory = scope_index.load_dependency_signature_inventory(index)
    worker = tiny_repo / "engine" / "worker.py"
    worker.write_text(
        "def calculate():\n    value = 2\n    return value\n",
        encoding="utf-8",
    )

    observed = scope_index.verify_changed_python_source(
        inventory,
        "engine/worker.py",
        worker.read_bytes(),
    )
    regenerated = _generate(tiny_repo, "body-only-regenerated.json")

    assert observed == inventory["engine/worker.py"]
    assert regenerated.read_bytes() == index.read_bytes()


def test_explicit_data_only_path_edit_does_not_mint_dependency_drift() -> None:
    from scripts.ci_scope_dependencies import dependency_structure_sha256

    first = "ARTIFACT = 'data/first.json'  # ci-trigger-closure: data\n"
    second = "ARTIFACT = 'data/second.json'  # ci-trigger-closure: data\n"

    assert dependency_structure_sha256("engine/worker.py", first) == (
        dependency_structure_sha256("engine/worker.py", second)
    )


def test_ambiguity_line_movement_does_not_mint_dependency_drift() -> None:
    from scripts.ci_scope_dependencies import dependency_structure_sha256

    first = "import subprocess\nsubprocess.run(['echo', 'probe'])\n"
    second = "import subprocess\n\n\nsubprocess.run(['echo', 'probe'])\n"

    assert dependency_structure_sha256("engine/worker.py", first) == (
        dependency_structure_sha256("engine/worker.py", second)
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "import engine.helper\n\ndef calculate():\n    return 1\n",
        "DEPENDENCY = 'engine/helper.py'\n\ndef calculate():\n    return 1\n",
        (
            "import subprocess\n\ndef calculate():\n"
            "    subprocess.run(['echo', 'probe'], check=True)\n    return 1\n"
        ),
    ],
    ids=["new-import", "new-path-read", "new-subprocess"],
)
def test_dependency_semantic_mutations_require_index_regeneration(
    tiny_repo: Path,
    mutation: str,
) -> None:
    index = _generate(tiny_repo)
    inventory = scope_index.load_dependency_signature_inventory(index)

    with pytest.raises(scope_index.ScopeIndexError, match="dependency structure drift"):
        scope_index.verify_changed_python_source(
            inventory,
            "engine/worker.py",
            mutation,
        )


def test_python_addition_and_deletion_require_index_regeneration(
    tiny_repo: Path,
) -> None:
    index = _generate(tiny_repo)
    inventory = scope_index.load_dependency_signature_inventory(index)

    with pytest.raises(scope_index.ScopeIndexError, match="was added"):
        scope_index.verify_changed_python_source(
            inventory,
            "engine/new_module.py",
            "VALUE = 1\n",
        )
    with pytest.raises(scope_index.ScopeIndexError, match="was deleted"):
        scope_index.verify_changed_python_source(
            inventory,
            "engine/worker.py",
            None,
        )


@pytest.mark.parametrize(
    ("submitted", "expected_status"),
    [
        (
            "def calculate():\n    value = 2\n    return value\n",
            "pass",
        ),
        (
            "import engine.helper\n\ndef calculate():\n    return 1\n",
            "fail",
        ),
    ],
    ids=["body-only", "dependency-drift"],
)
def test_sparse_preflight_reads_only_changed_python_blob_from_head(
    tiny_repo: Path,
    submitted: str,
    expected_status: str,
) -> None:
    index = _generate(tiny_repo)
    subprocess.run(["git", "init", "-q"], cwd=tiny_repo, check=True)
    subprocess.run(
        ["git", "config", "user.name", "CI Test"], cwd=tiny_repo, check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "ci-test@example.invalid"],
        cwd=tiny_repo,
        check=True,
    )
    subprocess.run(["git", "add", "."], cwd=tiny_repo, check=True)
    subprocess.run(["git", "commit", "-qm", "indexed fixture"], cwd=tiny_repo, check=True)

    worker = tiny_repo / "engine/worker.py"
    worker.write_text(submitted, encoding="utf-8")
    subprocess.run(["git", "add", str(worker)], cwd=tiny_repo, check=True)
    subprocess.run(["git", "commit", "-qm", "submitted change"], cwd=tiny_repo, check=True)
    worker.unlink()  # Simulate the planner's metadata-only sparse worktree.

    result = structural_preflight.run_preflight(
        tiny_repo,
        ["engine/worker.py"],
        scope_index_path=index,
    )

    assert result["status"] == expected_status
    assert result["metrics"]["changed_python_signatures_examined"] == 1
    stale = [
        finding
        for finding in result["findings"]
        if finding["code"] == "dependency_signature_stale"
    ]
    assert bool(stale) is (expected_status == "fail")


def test_unsafe_companion_path_cannot_hide_python_dependency_drift(
    tiny_repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    index = _generate(tiny_repo)
    (tiny_repo / "engine/worker.py").write_text(
        "import engine.helper\n\ndef calculate():\n    return 1\n",
        encoding="utf-8",
    )

    assert structural_preflight.main(
        [
            "--root",
            str(tiny_repo),
            "--changed-path",
            "engine/worker.py",
            "--changed-path",
            "scripts/decoy.py\nhas_work=false",
            "--scope-index",
            str(index),
        ]
    ) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "fail"
    assert result["classification"] == "input_failure"


@pytest.mark.parametrize("defect", ["duplicate", "missing"])
def test_duplicate_or_missing_job_inventory_fails_closed(
    tiny_repo: Path,
    defect: str,
) -> None:
    index = _generate(tiny_repo)
    payload = _read(index)
    if defect == "duplicate":
        payload["job_inventory"][1] = payload["job_inventory"][0]
        payload["jobs"][1]["job_id"] = payload["jobs"][0]["job_id"]
        expected = "duplicate job ids"
    else:
        payload["job_inventory"].pop()
        payload["jobs"].pop()
        payload["job_count"] -= 1
        expected = "inventory drift"
    _write_and_reseal(index, payload)

    with pytest.raises(scope_index.ScopeIndexError, match=expected):
        scope_index.load_scope_index(
            index,
            repo_root=tiny_repo,
            pack_module=ci_pack,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [("ordinal", 99), ("weight", 99)],
)
def test_ordinal_or_weight_mismatch_fails_closed(
    tiny_repo: Path,
    field: str,
    value: int,
) -> None:
    index = _generate(tiny_repo)
    payload = _read(index)
    payload["jobs"][0][field] = value
    _write_and_reseal(index, payload)

    with pytest.raises(scope_index.ScopeIndexError, match="job identity drift"):
        scope_index.load_scope_index(
            index,
            repo_root=tiny_repo,
            pack_module=ci_pack,
        )


@pytest.mark.parametrize(
    "bad_path",
    [
        "../secret",
        "/absolute",
        "engine\\module.py",
        "engine/./module.py",
        "engine//module.py",
        " tests/test_alpha.py",
        7,
    ],
)
def test_malformed_indexed_path_fails_closed(
    tiny_repo: Path,
    bad_path: object,
) -> None:
    index = _generate(tiny_repo)
    payload = _read(index)
    payload["jobs"][0]["paths"] = [bad_path]
    _write_and_reseal(index, payload)

    with pytest.raises(scope_index.ScopeIndexError, match="path"):
        scope_index.load_scope_index(
            index,
            repo_root=tiny_repo,
            pack_module=ci_pack,
        )


@pytest.mark.parametrize(
    "bad_paths",
    [
        ["engine/a.py", "engine/a.py"],
        ["tests/z.py", "engine/a.py"],
    ],
)
def test_duplicate_or_unsorted_paths_fail_closed(
    tiny_repo: Path,
    bad_paths: list[str],
) -> None:
    index = _generate(tiny_repo)
    payload = _read(index)
    payload["jobs"][0]["paths"] = bad_paths
    _write_and_reseal(index, payload)

    with pytest.raises(scope_index.ScopeIndexError, match="duplicates|sorted"):
        scope_index.load_scope_index(
            index,
            repo_root=tiny_repo,
            pack_module=ci_pack,
        )


def test_duplicate_json_object_key_fails_closed(tiny_repo: Path) -> None:
    index = _generate(tiny_repo)
    raw = index.read_text(encoding="utf-8")
    raw = raw.replace(
        '  "index_sha256":',
        '  "schema": "duplicate",\n  "index_sha256":',
        1,
    )
    index.write_text(raw, encoding="utf-8")

    with pytest.raises(scope_index.ScopeIndexError, match="duplicate JSON object key"):
        scope_index.load_scope_index(
            index,
            repo_root=tiny_repo,
            pack_module=ci_pack,
        )


def test_generation_rejects_inference_identity_or_path_duplicates(
    tiny_repo: Path,
) -> None:
    def changed_identity(jobs):
        return [replace(jobs[0], weight=999), jobs[1]], "bad identity"

    with pytest.raises(scope_index.ScopeIndexError, match="changed job id"):
        scope_index.generate_scope_index(
            output_path=tiny_repo.parent / "identity.json",
            repo_root=tiny_repo,
            pack_module=ci_pack,
            infer_scopes=changed_identity,
        )

    def duplicate_path(jobs):
        return [
            replace(jobs[0], paths=("engine/**", "engine/**")),
            jobs[1],
        ], "duplicate path"

    with pytest.raises(scope_index.ScopeIndexError, match="duplicate paths"):
        scope_index.generate_scope_index(
            output_path=tiny_repo.parent / "duplicate.json",
            repo_root=tiny_repo,
            pack_module=ci_pack,
            infer_scopes=duplicate_path,
        )
