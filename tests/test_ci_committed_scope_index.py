from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import ci_committed_scope_index as scope_index
from scripts import run_ci_pack as ci_pack


REPO_ROOT = Path(__file__).resolve().parents[1]


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
    for relative in scope_index.SELECTOR_SOURCES:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPO_ROOT / relative).read_bytes())
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
