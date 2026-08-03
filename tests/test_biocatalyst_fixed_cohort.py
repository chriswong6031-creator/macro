"""Bounded, hermetic tests for the dark B1S1 fixed-cohort declaration."""
from __future__ import annotations

from copy import deepcopy
import ast
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil

import pytest

from engine.biocatalyst import fixed_cohort
from engine.biocatalyst.fixed_cohort import (
    ADMISSION_SNAPSHOT_MAX_BYTES,
    FIXED_COHORT_CONTRACT_ID,
    FIXED_COHORT_MAX_NCT_IDS,
    FIXED_COHORT_MAX_QUERY_BYTES,
    FIXTURE_MAX_BYTES,
    FIXTURE_MAX_JSON_CONTAINER_ITEMS,
    FIXTURE_MAX_JSON_DEPTH,
    FIXTURE_MAX_JSON_NODES,
    FIXTURE_MAX_JSON_NUMBER_TOKEN_BYTES,
    FIXTURE_MAX_JSON_STRING_BYTES,
    REGISTRY_MAX_BYTES,
    FixedCohortFixtureError,
    admit_fixed_cohort_candidates,
    build_fixed_cohort,
    fixed_cohort_contract_semantic_issues,
    fixed_cohort_identity_payload,
    load_bounded_canonical_json_fixture,
    load_fixed_cohort_fixture,
    query_id_byte_issues,
    validate_fixed_cohort,
)
from engine.sector_intelligence.contracts import (
    ContractRegistry,
    ContractValidationError,
    canonical_json_bytes,
    canonical_json_sha256,
)
import scripts.biocatalyst_worker as worker


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "biocatalyst"
FIXTURE_NAME = "ctgov_fixed_cohort.v1.valid.json"


def _fixture() -> dict:
    return json.loads((FIXTURE_ROOT / FIXTURE_NAME).read_text(encoding="utf-8"))


def _rebind(document: dict) -> dict:
    document["cohort_id"] = (
        f"ctgov_fixed_cohort_{canonical_json_sha256(fixed_cohort_identity_payload(document))[:24]}"
    )
    document["cohort_payload_sha256"] = canonical_json_sha256(
        {key: value for key, value in document.items() if key != "cohort_payload_sha256"}
    )
    return document


def _assert_rejected(document: dict, code: str, *, repo_root: Path | str | None = None) -> None:
    with pytest.raises(ContractValidationError) as caught:
        validate_fixed_cohort(document, repo_root=repo_root)
    assert code in {issue.code for issue in caught.value.issues}


def _clone_repo_root(tmp_path: Path) -> Path:
    target = tmp_path / "repo"
    shutil.copytree(ROOT / "contracts", target / "contracts")
    registry = target / "config" / "biocatalyst_sources.yml"
    registry.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "config" / "biocatalyst_sources.yml", registry)
    return target


def _write_canonical(root: Path, relative: str, value: object, *, terminal_lf: bool = True) -> Path:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(canonical_json_bytes(value) + (b"\n" if terminal_lf else b""))
    return target


def test_valid_fixture_is_canonical_registered_and_generic_contract_valid() -> None:
    loaded = load_fixed_cohort_fixture(FIXTURE_ROOT.resolve())
    assert loaded == _fixture()
    assert ContractRegistry(ROOT).issues(FIXED_COHORT_CONTRACT_ID, loaded) == ()
    assert fixed_cohort_contract_semantic_issues(loaded, repo_root=ROOT) == []


def test_build_accepts_exact_one_and_twenty_five_canonical_ids() -> None:
    provenance = {"kind": "hermetic_fixture", "fixture_id": "boundary"}
    one = build_fixed_cohort(["NCT00000001"], provenance=provenance)
    many_ids = [f"NCT{value:08d}" for value in range(1, FIXED_COHORT_MAX_NCT_IDS + 1)]
    many = build_fixed_cohort(many_ids, provenance=provenance)

    assert one["nct_ids"] == ["NCT00000001"]
    assert many["nct_ids"] == many_ids
    assert many["query_id"] == ",".join(many_ids)
    assert len(many["query_id"].encode("utf-8")) == FIXED_COHORT_MAX_QUERY_BYTES


@pytest.mark.parametrize(
    "nct_ids, expected",
    [
        ([], "nct_ids must contain 1-25"),
        ([f"NCT{value:08d}" for value in range(1, 27)], "nct_ids must contain 1-25"),
        (["NCT00000001", "NCT00000001"], "nct_ids must be unique"),
        (["NCT00000002", "NCT00000001"], "nct_ids must be sorted"),
        (["NCT0000000１"], "canonical ASCII"),
    ],
)
def test_build_rejects_invalid_membership_before_any_admission(nct_ids, expected: str) -> None:
    with pytest.raises(ValueError, match=expected):
        build_fixed_cohort(
            nct_ids,
            provenance={"kind": "hermetic_fixture", "fixture_id": "invalid"},
        )


def test_validation_rejects_membership_query_source_identity_hash_and_registry_tampering(tmp_path: Path) -> None:
    duplicate = _fixture()
    duplicate["nct_ids"] = ["NCT00000001", "NCT00000001"]
    duplicate["query_id"] = "NCT00000001,NCT00000001"
    _assert_rejected(_rebind(duplicate), "fixed_cohort.nct_unique")

    unsorted = _fixture()
    unsorted["nct_ids"] = ["NCT00000002", "NCT00000001"]
    unsorted["query_id"] = "NCT00000002,NCT00000001"
    _assert_rejected(_rebind(unsorted), "fixed_cohort.nct_order")

    malformed = _fixture()
    malformed["nct_ids"] = ["NCT0000000１"]
    malformed["query_id"] = "NCT0000000１"
    _assert_rejected(_rebind(malformed), "fixed_cohort.nct_id")

    wrong_source = _fixture()
    wrong_source["source_id"] = "not_clinicaltrials"
    _assert_rejected(_rebind(wrong_source), "fixed_cohort.registration_binding")

    wrong_query = _fixture()
    wrong_query["query_id"] = "NCT00000002,NCT00000001"
    _assert_rejected(_rebind(wrong_query), "fixed_cohort.query_binding")

    wrong_hash = _fixture()
    wrong_hash["cohort_payload_sha256"] = "0" * 64
    _assert_rejected(wrong_hash, "fixed_cohort.hash")

    wrong_identity = _fixture()
    wrong_identity["cohort_id"] = "ctgov_fixed_cohort_" + "0" * 24
    _assert_rejected(wrong_identity, "fixed_cohort.identity")

    repo_root = _clone_repo_root(tmp_path)
    registry = repo_root / "config" / "biocatalyst_sources.yml"
    registry.write_bytes(registry.read_bytes() + b"# content mutation\n")
    _assert_rejected(_fixture(), "fixed_cohort.registry_hash", repo_root=repo_root)


def test_query_byte_limit_is_exact_and_counts_utf8_not_characters() -> None:
    assert query_id_byte_issues("a" * FIXED_COHORT_MAX_QUERY_BYTES) == ()
    assert query_id_byte_issues("é" * 149 + "a") == ()
    assert {issue.code for issue in query_id_byte_issues("a" * 300)} == {
        "fixed_cohort.query_bytes"
    }
    assert {issue.code for issue in query_id_byte_issues("é" * 150)} == {
        "fixed_cohort.query_bytes"
    }


def test_provenance_arms_are_exclusive_and_dark_registration_is_bound(tmp_path: Path) -> None:
    registered = build_fixed_cohort(
        ["NCT00000001"],
        provenance={
            "kind": "registered_control",
            "control_registration": "b1s1_fixed_cohort_control",
            "source_registry_ref": "config/biocatalyst_sources.yml",
        },
    )
    validate_fixed_cohort(registered)

    blended = _fixture()
    blended["provenance"]["control_registration"] = "b1s1_fixed_cohort_control"
    _assert_rejected(_rebind(blended), "fixed_cohort.provenance")

    repo_root = _clone_repo_root(tmp_path)
    registry = repo_root / "config" / "biocatalyst_sources.yml"
    prefix, b1s1_control = registry.read_text(encoding="utf-8").split(
        "b1s1_fixed_cohort_control:", 1
    )
    changed = prefix + "b1s1_fixed_cohort_control:" + b1s1_control.replace(
        "worker_mode_available: false", "worker_mode_available: true", 1
    )
    registry.write_text(changed, encoding="utf-8")
    bound = _fixture()
    bound["source_registry_sha256"] = sha256(registry.read_bytes()).hexdigest()
    _assert_rejected(_rebind(bound), "fixed_cohort.registration", repo_root=repo_root)


def test_admission_is_bounded_validated_cohort_subset_only() -> None:
    cohort = _fixture()
    assert admit_fixed_cohort_candidates(cohort, []) == ()
    assert admit_fixed_cohort_candidates(cohort, ["NCT00000002"]) == ("NCT00000002",)
    with pytest.raises(ValueError, match="may not enlarge"):
        admit_fixed_cohort_candidates(cohort, ["NCT00000002", "NCT99999999"])
    with pytest.raises(ValueError, match="canonical ASCII"):
        admit_fixed_cohort_candidates(cohort, ["bad"])
    with pytest.raises(ValueError, match="unique"):
        admit_fixed_cohort_candidates(cohort, ["NCT00000001", "NCT00000001"])
    with pytest.raises(ValueError, match="at most 25"):
        admit_fixed_cohort_candidates(
            cohort, [f"NCT{value:08d}" for value in range(1, 27)]
        )


def test_admission_uses_one_detached_snapshot_against_split_nct_mapping() -> None:
    class SplitNctMapping(dict):
        def __getitem__(self, key):
            if key == "nct_ids":
                return ["NCT00000001", "NCT00000002", "NCT99999999"]
            return super().__getitem__(key)

    split = SplitNctMapping(_fixture())
    # The generic validator sees get/items, while the former admission path
    # subsequently trusted __getitem__ and could return NCT99999999.
    validate_fixed_cohort(split)
    with pytest.raises(ValueError, match="may not enlarge"):
        admit_fixed_cohort_candidates(split, ["NCT99999999"])
    assert admit_fixed_cohort_candidates(split, ["NCT00000002"]) == ("NCT00000002",)


def test_build_and_admission_reject_deceptive_list_subclasses_and_bad_snapshots() -> None:
    class DeceptiveNctIds(list):
        def __len__(self):
            return 1

    class DeceptiveCandidates(list):
        def __len__(self):
            return 1

    with pytest.raises(ValueError, match="sequence"):
        build_fixed_cohort(
            DeceptiveNctIds(["NCT00000001"] * 26),
            provenance={"kind": "hermetic_fixture", "fixture_id": "deceptive"},
        )
    with pytest.raises(ValueError, match="list or tuple"):
        admit_fixed_cohort_candidates(_fixture(), DeceptiveCandidates(["NCT00000001"] * 26))

    nonfinite = _fixture()
    nonfinite["source_registry_sha256"] = float("nan")
    with pytest.raises(ValueError, match="finite canonical"):
        admit_fixed_cohort_candidates(nonfinite, [])

    cyclic: dict = _fixture()
    cyclic["cycle"] = cyclic
    with pytest.raises(ValueError, match="finite canonical"):
        admit_fixed_cohort_candidates(cyclic, [])

    oversized = _fixture()
    oversized["padding"] = "x" * ADMISSION_SNAPSHOT_MAX_BYTES
    with pytest.raises(ValueError, match="snapshot exceeds"):
        admit_fixed_cohort_candidates(oversized, [])


@pytest.mark.parametrize("error", [RuntimeError("explode"), ValueError("explode")])
def test_admission_bounds_exploding_mapping_canonicalization(error: Exception) -> None:
    class ExplodingItems(dict):
        def items(self):
            raise error

    with pytest.raises(ValueError, match="finite canonical"):
        admit_fixed_cohort_candidates(ExplodingItems(_fixture()), [])


def test_builder_copies_mutable_dark_control_values() -> None:
    first = build_fixed_cohort(
        ["NCT00000001"], provenance={"kind": "hermetic_fixture", "fixture_id": "first"}
    )
    first["control"]["consumers"].append("poison")
    second = build_fixed_cohort(
        ["NCT00000002"], provenance={"kind": "hermetic_fixture", "fixture_id": "second"}
    )
    assert second["control"]["consumers"] == []


def test_builder_rejects_oversized_or_blended_provenance_before_hashing() -> None:
    with pytest.raises(ValueError, match="bounded fixture_id"):
        build_fixed_cohort(
            ["NCT00000001"],
            provenance={"kind": "hermetic_fixture", "fixture_id": "x", "extra": "no"},
        )
    with pytest.raises(ValueError, match="bounded fixture_id"):
        build_fixed_cohort(
            ["NCT00000001"],
            provenance={"kind": "hermetic_fixture", "fixture_id": "x" * 97},
        )


def test_fixture_loader_rejects_unsafe_path_types_and_path_swap(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "fixtures"
    root.mkdir()
    _write_canonical(root, "safe.json", {"safe": True})
    assert load_bounded_canonical_json_fixture(root, "safe.json") == {"safe": True}
    with pytest.raises(FixedCohortFixtureError, match="absolute path"):
        load_bounded_canonical_json_fixture(Path("relative"), "safe.json")
    with pytest.raises(FixedCohortFixtureError, match="escapes"):
        load_bounded_canonical_json_fixture(root, "../safe.json")

    (root / "link.json").symlink_to(root / "safe.json")
    with pytest.raises(FixedCohortFixtureError, match="unsafe|cannot safely"):
        load_bounded_canonical_json_fixture(root, "link.json")
    fifo = root / "fixture.fifo"
    os.mkfifo(fifo)
    with pytest.raises(FixedCohortFixtureError, match="regular file"):
        load_bounded_canonical_json_fixture(root, fifo.name)

    target = _write_canonical(root, "swap.json", {"safe": True})
    original_read = fixed_cohort.os.read
    changed = False

    def swap_after_read(descriptor: int, count: int) -> bytes:
        nonlocal changed
        result = original_read(descriptor, count)
        if not changed:
            changed = True
            target.write_bytes(canonical_json_bytes({"safe": False}))
        return result

    monkeypatch.setattr(fixed_cohort.os, "read", swap_after_read)
    with pytest.raises(FixedCohortFixtureError, match="changed while being read"):
        load_bounded_canonical_json_fixture(root, target.name)


def test_fixture_loader_caps_and_noncanonical_inputs_at_exact_boundaries(tmp_path: Path) -> None:
    root = tmp_path / "fixtures"
    root.mkdir()
    _write_canonical(root, "terminal-lf.json", {"x": 1}, terminal_lf=True)
    assert load_bounded_canonical_json_fixture(root, "terminal-lf.json") == {"x": 1}
    _write_canonical(root, "missing-terminal-lf.json", {"x": 1}, terminal_lf=False)
    (root / "duplicate.json").write_bytes(b'{"x":1,"x":2}')
    (root / "noncanonical.json").write_bytes(b'{"x": 1}')
    (root / "nonfinite.json").write_bytes(b'{"x":NaN}')
    for name in ("missing-terminal-lf.json", "duplicate.json", "noncanonical.json", "nonfinite.json"):
        with pytest.raises(FixedCohortFixtureError):
            load_bounded_canonical_json_fixture(root, name)

    (root / "size-at-cap.json").write_bytes(b"x" * FIXTURE_MAX_BYTES)
    with pytest.raises(FixedCohortFixtureError) as accepted_size:
        load_bounded_canonical_json_fixture(root, "size-at-cap.json")
    assert {issue.code for issue in accepted_size.value.issues} == {"fixed_cohort.fixture_json"}
    (root / "size-over-cap.json").write_bytes(b"x" * (FIXTURE_MAX_BYTES + 1))
    with pytest.raises(FixedCohortFixtureError) as rejected_size:
        load_bounded_canonical_json_fixture(root, "size-over-cap.json")
    assert {issue.code for issue in rejected_size.value.issues} == {"fixed_cohort.fixture_size"}

    _write_canonical(root, "string-at-cap.json", {"x": "é" * (FIXTURE_MAX_JSON_STRING_BYTES // 2)})
    assert load_bounded_canonical_json_fixture(root, "string-at-cap.json")["x"] == "é" * 256
    _write_canonical(root, "string-over-cap.json", {"x": "é" * 256 + "a"})
    with pytest.raises(FixedCohortFixtureError, match="string exceeds"):
        load_bounded_canonical_json_fixture(root, "string-over-cap.json")

    _write_canonical(root, "array-at-cap.json", {"x": [0] * FIXTURE_MAX_JSON_CONTAINER_ITEMS})
    assert len(load_bounded_canonical_json_fixture(root, "array-at-cap.json")["x"]) == 32
    _write_canonical(root, "array-over-cap.json", {"x": [0] * (FIXTURE_MAX_JSON_CONTAINER_ITEMS + 1)})
    with pytest.raises(FixedCohortFixtureError, match="array exceeds"):
        load_bounded_canonical_json_fixture(root, "array-over-cap.json")

    node_at_cap = {f"a{index}": [0] * 32 for index in range(7)}
    node_at_cap["a7"] = [0] * 23
    _write_canonical(root, "nodes-at-cap.json", node_at_cap)
    assert load_bounded_canonical_json_fixture(root, "nodes-at-cap.json") == node_at_cap
    node_over_cap = deepcopy(node_at_cap)
    node_over_cap["a7"].append(0)
    _write_canonical(root, "nodes-over-cap.json", node_over_cap)
    with pytest.raises(FixedCohortFixtureError, match="node limit"):
        load_bounded_canonical_json_fixture(root, "nodes-over-cap.json")

    depth_at_cap: object = 0
    for _ in range(FIXTURE_MAX_JSON_DEPTH):
        depth_at_cap = {"x": depth_at_cap}
    _write_canonical(root, "depth-at-cap.json", depth_at_cap)
    assert load_bounded_canonical_json_fixture(root, "depth-at-cap.json") == depth_at_cap
    _write_canonical(root, "depth-over-cap.json", {"x": depth_at_cap})
    with pytest.raises(FixedCohortFixtureError, match="nesting-depth"):
        load_bounded_canonical_json_fixture(root, "depth-over-cap.json")

    (root / "number-at-cap.json").write_bytes(b'{"x":' + b"1" * FIXTURE_MAX_JSON_NUMBER_TOKEN_BYTES + b"}\n")
    assert load_bounded_canonical_json_fixture(root, "number-at-cap.json")["x"] == int("1" * FIXTURE_MAX_JSON_NUMBER_TOKEN_BYTES)
    (root / "number-over-cap.json").write_bytes(b'{"x":' + b"1" * (FIXTURE_MAX_JSON_NUMBER_TOKEN_BYTES + 1) + b"}\n")
    with pytest.raises(FixedCohortFixtureError, match="integer token"):
        load_bounded_canonical_json_fixture(root, "number-over-cap.json")


@pytest.mark.parametrize("fault", ["symlink", "fifo", "oversize"])
def test_registry_binding_reader_rejects_symlink_fifo_and_oversize(tmp_path: Path, fault: str) -> None:
    repo_root = _clone_repo_root(tmp_path)
    registry = repo_root / "config" / "biocatalyst_sources.yml"
    if fault == "symlink":
        outside = tmp_path / "outside.yml"
        outside.write_bytes(registry.read_bytes())
        registry.unlink()
        registry.symlink_to(outside)
    elif fault == "fifo":
        registry.unlink()
        os.mkfifo(registry)
    else:
        registry.write_bytes(b"#" * (REGISTRY_MAX_BYTES + 1))
    _assert_rejected(_fixture(), "fixed_cohort.registry_unavailable", repo_root=repo_root)


def test_fixed_cohort_module_has_no_live_or_entrypoint_import_boundary() -> None:
    source = (ROOT / "engine" / "biocatalyst" / "fixed_cohort.py").read_text(encoding="utf-8")
    imports = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    forbidden = {"requests", "http", "session", "collector", "worker", "store", "publisher", "router", "app"}
    assert all(not any(part in forbidden for part in imported.split(".")) for imported in imports)
    assert "if __name__" not in source


def test_existing_b1_canary_keeps_twenty_six_ids_without_a_fixed_cohort_manifest(tmp_path: Path, monkeypatch) -> None:
    state_root = tmp_path / "macro-biocatalyst" / "state"
    public_root = tmp_path / "macro-biocatalyst" / "public"
    monkeypatch.setattr(worker, "_SERVICE_STATE_ROOT", state_root)
    monkeypatch.setattr(worker, "_SERVICE_PUBLIC_ROOT", public_root)
    nct_ids = [f"NCT{value:08d}" for value in range(1, 27)]
    plan = worker.load_environment(
        {
            "BIOCATALYST_ENABLED": "1",
            "BIOCATALYST_STATE_ROOT": str(state_root),
            "BIOCATALYST_PUBLIC_ROOT": str(public_root),
            "BIOCATALYST_CANARY_NCTS": ",".join(nct_ids),
            "BIOCATALYST_USER_AGENT": "MastermindX test contact@example.com",
            "BIOCATALYST_R2_ENDPOINT": "https://r2.example.test",
            "BIOCATALYST_R2_BUCKET": "biocatalyst-private",
            "BIOCATALYST_R2_ACCESS_KEY_ID": "test-access",
            "BIOCATALYST_R2_SECRET_ACCESS_KEY": "test-secret",
        }
    )
    assert plan.state == "enabled"
    assert plan.configured_nct_count == 26
    assert plan.config is not None
    assert plan.config.nct_ids == tuple(nct_ids)
