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
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "CI Test"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "ci-test@example.invalid"],
        cwd=root,
        check=True,
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "base fixture"], cwd=root, check=True)
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


def _install_static_candidate_fixture(tiny_repo: Path) -> tuple[Path, Path, Path]:
    config = tiny_repo / "config"
    config.mkdir(exist_ok=True)
    present = config / "present.yml"
    missing = config / "missing.yml"
    link = config / "link.yml"
    present.write_text("value: one\n", encoding="utf-8")
    (tiny_repo / "engine/worker.py").write_text(
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parents[1]\n"
        "PRESENT = 'config/present.yml'\n"
        "MISSING = ROOT / 'config' / 'missing.yml'\n"
        "LINK = 'config/link.yml'\n"
        "DATA = 'config/runtime.json'  # ci-trigger-closure: data\n"
        "def calculate():\n"
        "    return 1\n",
        encoding="utf-8",
    )
    _commit_fixture(tiny_repo, "install static candidates")
    return present, missing, link


def _commit_fixture(tiny_repo: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=tiny_repo, check=True)
    subprocess.run(["git", "commit", "-qm", message], cwd=tiny_repo, check=True)


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


def test_generation_and_verify_bind_present_and_absent_static_path_candidates(
    tiny_repo: Path,
) -> None:
    _install_static_candidate_fixture(tiny_repo)
    index = _generate(tiny_repo)
    payload = _read(index)
    inventory = scope_index.load_static_path_candidate_inventory(index)
    receipt = scope_index.verify_scope_index(
        index,
        repo_root=tiny_repo,
        pack_module=ci_pack,
    )

    assert payload["schema"] == "ci.committed_scope_index.v3"
    assert payload["static_path_candidates"]["schema"] == (
        "ci.static_path_candidate_inventory.v1"
    )
    assert inventory["config/present.yml"] is True
    assert inventory["config/missing.yml"] is False
    assert inventory["config/link.yml"] is False
    assert "config/runtime.json" not in inventory
    assert receipt.static_path_candidate_count == len(inventory)
    assert scope_index.verify_changed_static_path_candidate(
        inventory, "config/present.yml", True
    ) == "present"
    assert scope_index.verify_changed_static_path_candidate(
        inventory, "config/missing.yml", False
    ) == "absent"


def test_exact_git_tree_case_identity_drives_candidates_jobs_and_verify(
    tiny_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import ci_scope_dependencies as dependencies

    upper = tiny_repo / "research/winners/cases/NVDA_2023.md"
    lower_rel = "research/winners/cases/nvda_2023.md"
    upper.parent.mkdir(parents=True)
    upper.write_text("# exact uppercase entry\n", encoding="utf-8")
    worker = tiny_repo / "engine/worker.py"
    worker.write_text(f"CASE = {lower_rel!r}\n", encoding="utf-8")
    _commit_fixture(tiny_repo, "case-sensitive candidate fixture")

    monkeypatch.setattr(dependencies, "ROOT", tiny_repo)

    def infer(jobs):
        reads = tuple(sorted(dependencies.direct_reads(worker)))
        return [replace(jobs[0], paths=reads), replace(jobs[1], paths=())], "exact tree"

    index = tiny_repo.parent / "case-index.json"
    document = scope_index.generate_scope_index(
        output_path=index,
        repo_root=tiny_repo,
        pack_module=ci_pack,
        infer_scopes=infer,
    )
    inventory = scope_index.load_static_path_candidate_inventory(index)

    assert inventory[lower_rel] is False
    assert lower_rel not in document["jobs"][0]["paths"]
    scope_index.verify_scope_index(index, repo_root=tiny_repo, pack_module=ci_pack)

    tampered = _read(index)
    record = next(
        item
        for item in tampered["static_path_candidates"]["candidates"]
        if item["path"] == lower_rel
    )
    record["present"] = True
    _write_and_reseal(index, tampered)
    with pytest.raises(scope_index.ScopeIndexError, match="presence drift"):
        scope_index.verify_scope_index(index, repo_root=tiny_repo, pack_module=ci_pack)

    fresh = tiny_repo.parent / "case-index-fresh.json"
    scope_index.generate_scope_index(
        output_path=fresh,
        repo_root=tiny_repo,
        pack_module=ci_pack,
        infer_scopes=infer,
    )
    temporary = "research/winners/cases/case-rename.tmp"
    subprocess.run(
        ["git", "mv", upper.relative_to(tiny_repo), temporary],
        cwd=tiny_repo,
        check=True,
    )
    subprocess.run(["git", "mv", temporary, lower_rel], cwd=tiny_repo, check=True)
    _commit_fixture(tiny_repo, "make lowercase entry exact")
    with pytest.raises(scope_index.ScopeIndexError, match="presence drift"):
        scope_index.verify_scope_index(fresh, repo_root=tiny_repo, pack_module=ci_pack)


def test_verify_rejects_exact_git_tree_python_inventory_drift(tiny_repo: Path) -> None:
    index = _generate(tiny_repo)
    added = tiny_repo / "engine/new_module.py"
    added.write_text("VALUE = 1\n", encoding="utf-8")
    _commit_fixture(tiny_repo, "add tracked Python source")

    with pytest.raises(scope_index.ScopeIndexError, match="Git-tree inventory drift"):
        scope_index.verify_scope_index(index, repo_root=tiny_repo, pack_module=ci_pack)


@pytest.mark.parametrize(
    ("mode", "expected"),
    [(0o120000, "symbolic link"), (0o160000, "gitlink")],
)
def test_exact_git_tree_rejects_unsafe_candidate_modes(
    mode: int, expected: str
) -> None:
    from scripts.ci_scope_dependencies import GitTreeError, git_tree_regular_file

    with pytest.raises(GitTreeError, match=expected):
        git_tree_regular_file({"config/link": mode}, "config/link/value.yml")


def test_static_path_candidate_tamper_is_digest_bound(tiny_repo: Path) -> None:
    _install_static_candidate_fixture(tiny_repo)
    index = _generate(tiny_repo)
    payload = _read(index)
    record = next(
        item
        for item in payload["static_path_candidates"]["candidates"]
        if item["path"] == "config/present.yml"
    )
    record["present"] = False
    index.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(scope_index.ScopeIndexError, match="digest mismatch"):
        scope_index.load_static_path_candidate_inventory(index)


def test_static_path_candidate_inventory_rejects_noncanonical_resealed_path(
    tiny_repo: Path,
) -> None:
    _install_static_candidate_fixture(tiny_repo)
    index = _generate(tiny_repo)
    payload = _read(index)
    payload["static_path_candidates"]["candidates"][0]["path"] = (
        "config/" + "../outside.yml"
    )
    _write_and_reseal(index, payload)

    with pytest.raises(scope_index.ScopeIndexError, match="canonical"):
        scope_index.load_static_path_candidate_inventory(index)


def test_static_path_candidate_addition_and_deletion_require_regeneration(
    tiny_repo: Path,
) -> None:
    _install_static_candidate_fixture(tiny_repo)
    index = _generate(tiny_repo)
    inventory = scope_index.load_static_path_candidate_inventory(index)

    with pytest.raises(scope_index.ScopeIndexError, match="missing.yml was added"):
        scope_index.verify_changed_static_path_candidate(
            inventory, "config/missing.yml", True
        )
    with pytest.raises(scope_index.ScopeIndexError, match="present.yml was deleted"):
        scope_index.verify_changed_static_path_candidate(
            inventory, "config/present.yml", False
        )


@pytest.mark.parametrize(
    ("mutation", "changed", "expected_status", "expected_code"),
    [
        ("add", "config/missing.yml", "fail", "static_path_candidate_stale"),
        ("delete", "config/present.yml", "fail", "static_path_candidate_stale"),
        ("modify", "config/present.yml", "pass", None),
        ("symlink", "config/link.yml", "fail", "static_path_candidate_unsafe"),
    ],
)
def test_preflight_checks_static_candidate_topology_from_submitted_head(
    tiny_repo: Path,
    mutation: str,
    changed: str,
    expected_status: str,
    expected_code: str | None,
) -> None:
    present, missing, link = _install_static_candidate_fixture(tiny_repo)
    index = _generate(tiny_repo)

    if mutation == "add":
        missing.write_text("value: added\n", encoding="utf-8")
    elif mutation == "delete":
        present.unlink()
    elif mutation == "modify":
        present.write_text("value: modified\n", encoding="utf-8")
    else:
        link.symlink_to("present.yml")
    _commit_fixture(tiny_repo, f"{mutation} candidate")

    submitted = tiny_repo / changed
    submitted.unlink(missing_ok=True)  # prove the check reads HEAD, not sparse state
    result = structural_preflight.run_preflight(
        tiny_repo,
        [changed],
        scope_index_path=index,
    )

    assert result["status"] == expected_status
    assert result["metrics"]["changed_static_path_candidates_examined"] == 1
    codes = {finding["code"] for finding in result["findings"]}
    if expected_code is None:
        assert not {"static_path_candidate_stale", "static_path_candidate_unsafe"} & codes
    else:
        assert expected_code in codes


def test_generation_rejects_static_candidate_symlink(tiny_repo: Path) -> None:
    _present, _missing, link = _install_static_candidate_fixture(tiny_repo)
    link.symlink_to("present.yml")
    _commit_fixture(tiny_repo, "add candidate symlink")

    with pytest.raises(scope_index.ScopeIndexError, match="symbolic link"):
        _generate(tiny_repo)


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
        "engine/" + "./module.py",
        "engine/" + "/module.py",
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
