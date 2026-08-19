"""Hostile contracts for the shared CI semantic-proof law."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts import ci_semantic_proof as proof


TREE = "1" * 40
HEAD = "2" * 40
BASE = "3" * 40
PLAN_SHA = "4" * 64
JOB_SHA = "5" * 64
STEP_SHA = "6" * 64
OTHER_STEP_SHA = "7" * 64


def _plan(*, role: str = "pr_head", authority: bool = False) -> dict:
    document = {
        "schema": proof.PLAN_SCHEMA,
        "workflow_run_id": "99",
        "workflow": "ci",
        "event": "pull_request" if role == "pr_head" else "workflow_dispatch",
        "role": role,
        "tested_tree_sha": TREE,
        "subject_head_sha": HEAD if role == "pr_head" else TREE,
        "base_sha": BASE if role == "pr_head" else TREE,
        "authority_changed": authority,
        "changed_from": BASE if role == "pr_head" else None,
        "scope_mode": "active",
        "reason": "focused semantic fixture",
        "scope_summary": "focused semantic fixture",
        "legacy_job_count": 1,
        "eligible_job_count": 1,
        "changed_files_sha256": "",
        "changed_files_count": 0,
        "eligible_jobs": ["job-a"],
        "skipped_job_count": 0,
        "skipped_jobs": [],
        "packs": [
            {"index": index, "weight": 0 if index < 5 else 1, "jobs": [] if index < 5 else ["job-a"]}
            for index in range(6)
        ],
        "nonempty_pack_indices": [5],
        "matrix": {"include": [{"pack": 5}]},
        "has_work": True,
        "plan_sha256": PLAN_SHA,
        "semantic_jobs": [
            {
                "logical_job_id": "job-a",
                "pack_index": 5,
                "job_exec_sha256": JOB_SHA,
                "steps": [
                    {"proof_id": "proof-a", "step_spec_sha256": STEP_SHA},
                    {"proof_id": "proof-b", "step_spec_sha256": OTHER_STEP_SHA},
                ],
            }
        ],
    }
    document["plan_sha256"] = proof.authoritative_plan_sha256(document)
    return document


def _signature(atom: str = "pytest:failed:tests/test_x.py::test_a") -> dict:
    atoms = [atom]
    return {"atoms": atoms, "sha256": proof.canonical_sha256(atoms)}


def _base_replay(
    *,
    a_outcome: str = "failed",
    a_signature: object = None,
    a_spec: str = STEP_SHA,
    job_sha: str = JOB_SHA,
    include_a: bool = True,
) -> dict:
    steps = []
    if include_a:
        steps.append(
            {
                "proof_id": "proof-a",
                "step_spec_sha256": a_spec,
                "outcome": a_outcome,
                "failure_signature": a_signature,
            }
        )
    steps.append(
        {
            "proof_id": "proof-b",
            "step_spec_sha256": OTHER_STEP_SHA,
            "outcome": "passed",
            "failure_signature": None,
        }
    )
    return {
        "tested_tree_sha": BASE,
        "job_present": True,
        "logical_job_id": "job-a",
        "job_exec_sha256": job_sha,
        "infrastructure": {"outcome": "passed"},
        "steps": steps,
    }


def _fragment(
    *,
    a_outcome: str = "passed",
    a_signature: object = None,
    replay: object = None,
    role: str = "pr_head",
    plan: dict | None = None,
) -> dict:
    identity = plan or _plan(role=role)
    step_a = {
        "proof_id": "proof-a",
        "step_spec_sha256": STEP_SHA,
        "outcome": a_outcome,
        "failure_signature": a_signature,
    }
    if replay is not None:
        step_a["base_replay"] = replay
    return {
        "schema": proof.FRAGMENT_SCHEMA,
        **{key: identity[key] for key in (
            "workflow_run_id",
            "workflow",
            "event",
            "role",
            "tested_tree_sha",
            "subject_head_sha",
            "base_sha",
            "plan_sha256",
        )},
        "pack_index": 5,
        "infrastructure": [],
        "jobs": [
            {
                "logical_job_id": "job-a",
                "job_exec_sha256": JOB_SHA,
                "infrastructure": {"outcome": "passed"},
                "steps": [
                    step_a,
                    {
                        "proof_id": "proof-b",
                        "step_spec_sha256": OTHER_STEP_SHA,
                        "outcome": "passed",
                        "failure_signature": None,
                    },
                ],
            }
        ],
    }


def _reconcile(fragment: dict, *, plan: dict | None = None) -> dict:
    return proof.reconcile_evidence(plan or _plan(), [fragment])


def test_effective_proof_id_prefers_explicit_and_normalizes_name() -> None:
    assert proof.effective_proof_id({"name": "  stable   name ", "run": "true"}) == "stable name"
    assert proof.effective_proof_id(
        {"name": "renamed", "proof_id": "semantic-contract", "run": "true"}
    ) == "semantic-contract"
    with pytest.raises(proof.SemanticProofError):
        proof.effective_proof_id({"run": "true"})


def test_display_rename_does_not_change_explicit_identity_or_spec() -> None:
    first = {"name": "old", "proof_id": "proof-a", "run": "pytest -q"}
    renamed = {"name": "new", "proof_id": "proof-a", "run": "pytest -q"}
    changed = {"name": "old", "proof_id": "proof-a", "run": "pytest -x"}
    assert proof.effective_proof_id(first) == proof.effective_proof_id(renamed)
    assert proof.step_spec_sha256(first) == proof.step_spec_sha256(renamed)
    assert proof.step_spec_sha256(first) != proof.step_spec_sha256(changed)


def test_job_digest_binds_dependency_timeout_and_runner() -> None:
    base = proof.job_exec_sha256(
        dependency_install_command="pip install pytest",
        timeout_minutes=10,
        runner_contract="ubuntu/python312",
    )
    assert base != proof.job_exec_sha256(
        dependency_install_command="pip install pytest==9",
        timeout_minutes=10,
        runner_contract="ubuntu/python312",
    )
    assert base != proof.job_exec_sha256(
        dependency_install_command="pip install pytest",
        timeout_minutes=11,
        runner_contract="ubuntu/python312",
    )


def test_failure_collector_extracts_bounded_sorted_atoms_and_ignores_wrapper() -> None:
    collector = proof.FailureAtomCollector(max_bytes=4096, max_atoms=3, max_line_bytes=512)
    collector.feed(b"FAILED tests/test_z.py::test_b - AssertionError\n")
    collector.feed(b"ERROR tests/test_a.py::test_collection\n")
    collector.feed(b"::error title=legacy-job-job-a::step x exited 1\n")
    collector.feed(b"::error title=registry::stable invariant failed\n")
    signature = collector.signature()
    assert signature is not None
    assert signature["atoms"] == sorted(signature["atoms"])
    assert len(signature["atoms"]) == 3
    assert not any("legacy-job" in atom for atom in signature["atoms"])
    assert signature["sha256"] == proof.canonical_sha256(signature["atoms"])


def test_failure_collector_unknown_command_returns_null() -> None:
    collector = proof.FailureAtomCollector(max_bytes=16, max_atoms=2, max_line_bytes=8)
    collector.feed(b"password=do-not-store-this")
    assert collector.signature() is None


def test_benign_stream_volume_cannot_starve_a_late_failure_atom() -> None:
    collector = proof.FailureAtomCollector(max_bytes=256, max_atoms=2, max_line_bytes=128)
    for _ in range(2_000):
        collector.feed(b"ordinary progress output that is never retained\n")
    collector.feed(b"FAILED tests/test_late.py::test_real_failure - AssertionError\n")
    signature = collector.signature()
    assert signature is not None
    assert len(signature["atoms"]) == 1
    assert signature["atoms"][0].startswith(
        "pytest:failed:tests/test_late.py::test_real_failure:reason="
    )


def test_same_pytest_nodeid_with_different_failure_reason_has_different_signature() -> None:
    def collect(reason: str) -> object:
        collector = proof.FailureAtomCollector(max_bytes=4096, max_atoms=4, max_line_bytes=1024)
        collector.feed(f"FAILED tests/test_x.py::test_y - {reason}\n")
        return collector.signature()

    assert collect("AssertionError: old") != collect("ValueError: new")


def test_failure_atom_overflow_returns_null_instead_of_a_comparable_prefix() -> None:
    collector = proof.FailureAtomCollector(max_bytes=4096, max_atoms=2, max_line_bytes=1024)
    for index in range(3):
        collector.feed(f"FAILED tests/test_x.py::test_{index} - AssertionError\n")
    assert collector.signature() is None


def test_overlong_recognized_atom_is_null_but_long_benign_output_is_ignored() -> None:
    collector = proof.FailureAtomCollector(max_bytes=4096, max_atoms=4, max_line_bytes=64)
    collector.feed("ordinary progress " + "x" * 200)
    collector.feed("FAILED tests/test_x.py::test_y - " + "a" * 200)
    assert collector.signature() is None

    signable = proof.FailureAtomCollector(max_bytes=4096, max_atoms=4, max_line_bytes=64)
    signable.feed("ordinary progress " + "x" * 200)
    signable.feed("FAILED tests/test_x.py::test_y - short")
    assert signable.signature() is not None


@pytest.mark.parametrize(
    ("replay", "expected"),
    [
        ({"tested_tree_sha": BASE, "job_present": False}, "pr_ci_contract_change"),
        (_base_replay(include_a=False), "pr_ci_contract_change"),
        (_base_replay(a_spec="8" * 64), "pr_ci_contract_change"),
        (_base_replay(job_sha="9" * 64), "unknown"),
        (_base_replay(a_outcome="passed"), "pr_regression"),
        (_base_replay(a_outcome="not_run_prior_failure"), "unknown"),
        (_base_replay(a_signature=None), "unknown"),
        (_base_replay(a_signature=_signature("pytest:failed:tests/test_x.py::test_other")), "unknown"),
        (_base_replay(a_signature=_signature()), "inherited_base"),
    ],
)
def test_exact_base_cases_a_through_i(replay: dict, expected: str) -> None:
    signature = _signature()
    evidence = _reconcile(
        _fragment(a_outcome="failed", a_signature=signature, replay=replay)
    )
    assert evidence["jobs"][0]["steps"][0]["classification"] == expected
    assert evidence["status"] == ("clear" if expected == "inherited_base" else "failure")


def test_same_step_base_plus_new_failure_is_not_inherited() -> None:
    head = {"atoms": ["a", "b"], "sha256": proof.canonical_sha256(["a", "b"])}
    base = {"atoms": ["a"], "sha256": proof.canonical_sha256(["a"])}
    evidence = _reconcile(
        _fragment(
            a_outcome="failed",
            a_signature=head,
            replay=_base_replay(a_signature=base),
        )
    )
    step = evidence["jobs"][0]["steps"][0]
    assert step["classification"] == "unknown"
    assert "differ" in step["detail"]


def test_exact_base_replay_tree_mismatch_is_refused() -> None:
    replay = _base_replay(a_signature=_signature())
    replay["tested_tree_sha"] = "f" * 40
    with pytest.raises(proof.SemanticProofError, match="replay tree identity mismatch"):
        _reconcile(
            _fragment(
                a_outcome="failed",
                a_signature=_signature(),
                replay=replay,
            )
        )


def test_authority_change_cannot_self_excuse_but_all_pass_can_bootstrap() -> None:
    authority_plan = _plan(authority=True)
    fragment = _fragment(
        a_outcome="failed",
        a_signature=_signature(),
        replay=_base_replay(a_signature=_signature()),
        plan=authority_plan,
    )
    inherited = proof.reconcile_evidence(authority_plan, [fragment])
    assert inherited["status"] == "failure"
    assert any(row["outcome"] == "authority_self_excuse_refused" for row in inherited["infrastructure"])
    all_pass = proof.reconcile_evidence(authority_plan, [_fragment(plan=authority_plan)])
    assert all_pass["status"] == "clear"


def test_missing_fragment_and_missing_unit_are_explicit_not_pass() -> None:
    missing_pack = proof.reconcile_evidence(_plan(), [])
    assert missing_pack["status"] == "failure"
    assert proof.semantic_gate_verdict(missing_pack).infrastructure_blocking is True
    assert {step["outcome"] for step in missing_pack["jobs"][0]["steps"]} == {"infrastructure_blocked"}
    fragment = _fragment()
    fragment["jobs"][0]["steps"].pop()
    missing_step = _reconcile(fragment)
    assert missing_step["jobs"][0]["steps"][1]["classification"] == "unknown"


def test_duplicate_pack_job_step_unknown_and_out_of_plan_refuse() -> None:
    fragment = _fragment()
    with pytest.raises(proof.SemanticProofError, match="duplicate fragment"):
        proof.reconcile_evidence(_plan(), [fragment, fragment])
    duplicate_job = _fragment()
    duplicate_job["jobs"].append(copy.deepcopy(duplicate_job["jobs"][0]))
    with pytest.raises(proof.SemanticProofError, match="duplicate fragment job"):
        _reconcile(duplicate_job)
    duplicate_step = _fragment()
    duplicate_step["jobs"][0]["steps"].append(copy.deepcopy(duplicate_step["jobs"][0]["steps"][0]))
    with pytest.raises(proof.SemanticProofError, match="duplicate semantic proof"):
        _reconcile(duplicate_step)
    unknown = _fragment()
    unknown["jobs"][0]["steps"][0]["proof_id"] = "not-planned"
    with pytest.raises(proof.SemanticProofError, match="unknown semantic proof"):
        _reconcile(unknown)
    out_of_plan = _fragment()
    out_of_plan["pack_index"] = 9
    with pytest.raises(proof.SemanticProofError, match="out of plan"):
        _reconcile(out_of_plan)


def test_raw_log_or_unknown_fields_are_rejected_at_every_ingress() -> None:
    plan_mutations = []
    top_plan = _plan()
    top_plan["raw_log"] = "secret"
    plan_mutations.append(top_plan)
    job_plan = _plan()
    job_plan["semantic_jobs"][0]["raw_log"] = "secret"
    plan_mutations.append(job_plan)
    step_plan = _plan()
    step_plan["semantic_jobs"][0]["steps"][0]["raw_log"] = "secret"
    plan_mutations.append(step_plan)
    for mutation in plan_mutations:
        with pytest.raises(proof.SemanticProofError, match="unsupported fields"):
            proof.reconcile_evidence(mutation, [_fragment()])

    mutations = []
    top = _fragment()
    top["raw_log"] = "secret"
    mutations.append(top)
    job = _fragment()
    job["jobs"][0]["raw_log"] = "secret"
    mutations.append(job)
    step = _fragment()
    step["jobs"][0]["steps"][0]["raw_log"] = "secret"
    mutations.append(step)
    replay = _base_replay(a_signature=_signature())
    replay["raw_log"] = "secret"
    nested = _fragment(
        a_outcome="failed",
        a_signature=_signature(),
        replay=replay,
    )
    mutations.append(nested)
    for mutation in mutations:
        with pytest.raises(proof.SemanticProofError, match="unsupported fields"):
            _reconcile(mutation)

    evidence = _reconcile(_fragment())
    evidence["raw_log"] = "secret"
    evidence["evidence_sha256"] = proof.canonical_sha256(
        {key: value for key, value in evidence.items() if key != "evidence_sha256"}
    )
    with pytest.raises(proof.SemanticProofError, match="unsupported fields"):
        proof.load_semantic_evidence(evidence, advertised=True)


def test_fragment_tree_plan_and_job_digest_mismatches_refuse() -> None:
    for key, value, phrase in (
        ("tested_tree_sha", "a" * 40, "tested_tree_sha"),
        ("plan_sha256", "b" * 64, "plan_sha256"),
    ):
        fragment = _fragment()
        fragment[key] = value
        with pytest.raises(proof.SemanticProofError, match=phrase):
            _reconcile(fragment)
    fragment = _fragment()
    fragment["jobs"][0]["job_exec_sha256"] = "c" * 64
    with pytest.raises(proof.SemanticProofError, match="job digest"):
        _reconcile(fragment)


def test_evidence_digest_and_provenance_are_strict() -> None:
    evidence = _reconcile(_fragment())
    loaded = proof.load_semantic_evidence(
        evidence,
        advertised=True,
        expected_run_id=99,
        expected_subject_head_sha=HEAD,
        expected_tested_tree_sha=TREE,
        expected_base_sha=BASE,
        expected_role="pr_head",
        expected_workflow="ci",
        expected_event="pull_request",
    )
    assert loaded.mode == "semantic"
    tampered = copy.deepcopy(evidence)
    tampered["jobs"][0]["steps"][0]["detail"] = "tampered after sealing"
    with pytest.raises(proof.SemanticProofError, match="digest mismatch"):
        proof.load_semantic_evidence(tampered, advertised=True)
    with pytest.raises(proof.SemanticProofError, match="base_sha mismatch"):
        proof.load_semantic_evidence(
            evidence, advertised=True, expected_base_sha="f" * 40
        )


def test_plan_digest_and_role_event_are_recomputed_not_trusted() -> None:
    plan = _plan()
    changed = copy.deepcopy(plan)
    changed["semantic_jobs"][0]["steps"][0]["step_spec_sha256"] = "a" * 64
    with pytest.raises(proof.SemanticProofError, match="plan digest mismatch"):
        proof.reconcile_evidence(changed, [_fragment()])

    invalid_event = _plan()
    invalid_event["event"] = "workflow_dispatch"
    with pytest.raises(proof.SemanticProofError, match="role/event combination"):
        proof.authoritative_plan_sha256(invalid_event)


def test_legacy_absence_is_distinct_from_advertised_missing_or_malformed() -> None:
    assert proof.load_semantic_evidence(None, advertised=False).mode == "legacy_absent"
    with pytest.raises(proof.SemanticProofError, match="missing"):
        proof.load_semantic_evidence(None, advertised=True)
    with pytest.raises(proof.SemanticProofError):
        proof.load_semantic_evidence({"schema": proof.EVIDENCE_SCHEMA}, advertised=True)


def test_shared_json_decoder_rejects_duplicate_keys_and_non_objects() -> None:
    with pytest.raises(proof.SemanticProofError, match="duplicate JSON key"):
        proof.parse_semantic_json(b'{"schema":"a","schema":"b"}')
    with pytest.raises(proof.SemanticProofError, match="must be a JSON object"):
        proof.parse_semantic_json(b"[]")


def test_main_red_overlap_uses_candidate_full_semantic_surface() -> None:
    main_plan = _plan(role="main")
    main = proof.reconcile_evidence(
        main_plan,
        [_fragment(role="main", a_outcome="failed", a_signature=_signature())],
    )
    candidate = _reconcile(_fragment())
    assert proof.red_semantic_units(main) == {("job-a", "proof-a")}
    assert proof.main_red_overlap(main, candidate) == {("job-a", "proof-a")}
    unrelated = copy.deepcopy(candidate)
    unrelated["jobs"][0]["logical_job_id"] = "job-b"
    unrelated["evidence_sha256"] = proof.canonical_sha256(
        {key: value for key, value in unrelated.items() if key != "evidence_sha256"}
    )
    assert not proof.main_red_overlap(main, unrelated)


def test_descendant_pass_inside_overall_red_heals_monotonically() -> None:
    old = _reconcile(
        _fragment(
            a_outcome="failed",
            a_signature=_signature(),
            replay=_base_replay(a_signature=_signature("different")),
        )
    )
    passed = _reconcile(_fragment())
    passed["role"] = "main"
    passed["event"] = "workflow_dispatch"
    passed["tested_tree_sha"] = "a" * 40
    passed["subject_head_sha"] = "a" * 40
    passed["base_sha"] = "a" * 40
    # Overall-red sibling proof does not erase this unit's positive evidence.
    passed["status"] = "failure"
    passed["infrastructure"] = [{"outcome": "unrelated_red"}]
    passed["evidence_sha256"] = proof.canonical_sha256(
        {key: value for key, value in passed.items() if key != "evidence_sha256"}
    )
    later_red = copy.deepcopy(passed)
    later_red["tested_tree_sha"] = "b" * 40
    later_red["subject_head_sha"] = "b" * 40
    later_red["base_sha"] = "b" * 40
    later_red["jobs"][0]["steps"][0]["outcome"] = "failed"
    later_red["jobs"][0]["steps"][0]["classification"] = "main_failure"
    later_red["evidence_sha256"] = proof.canonical_sha256(
        {key: value for key, value in later_red.items() if key != "evidence_sha256"}
    )
    witness = proof.find_descendant_pass_witness(
        "job-a",
        "proof-a",
        "c" * 40,
        [later_red, passed],
        lambda ancestor, descendant: ancestor == "c" * 40 and descendant == "a" * 40,
        old_step_spec_sha=STEP_SHA,
    )
    assert witness is not None and witness.tested_tree_sha == "a" * 40
    assert witness.contract_changed is False
    assert proof.semantic_gate_verdict(old).clear is False


def test_non_descendant_pass_and_bounded_history_do_not_heal() -> None:
    main_plan = _plan(role="main")
    candidate = proof.reconcile_evidence(
        main_plan,
        [_fragment(role="main", plan=main_plan)],
    )
    assert proof.find_descendant_pass_witness(
        "job-a", "proof-a", BASE, [candidate] * 20, lambda *_: False, max_candidates=12
    ) is None


def test_reconcile_cli_always_writes_failure_artifact_on_malformed_input(
    tmp_path: Path,
) -> None:
    plan = tmp_path / "missing-plan.json"
    output = tmp_path / "final" / "ci-semantic-evidence.json"
    rc = proof.main(
        [
            "reconcile",
            "--plan",
            str(plan),
            "--fragments-dir",
            str(tmp_path / "fragments"),
            "--output",
            str(output),
        ]
    )
    assert rc == 2 and output.is_file()
    document = json.loads(output.read_text())
    assert document["status"] == "failure"
    assert document["infrastructure"][0]["outcome"] == "planner_configuration_failure"


def test_reconcile_cli_plan_failure_keeps_independently_bound_identity(
    tmp_path: Path,
) -> None:
    output = tmp_path / "final" / "ci-semantic-evidence.json"
    rc = proof.main(
        [
            "reconcile",
            "--plan",
            str(tmp_path / "missing-plan.json"),
            "--fragments-dir",
            str(tmp_path / "fragments"),
            "--output",
            str(output),
            "--fallback-workflow-run-id",
            "99",
            "--fallback-workflow",
            "ci",
            "--fallback-event",
            "pull_request",
            "--fallback-role",
            "pr_head",
            "--fallback-tested-tree-sha",
            TREE,
            "--fallback-subject-head-sha",
            HEAD,
            "--fallback-base-sha",
            BASE,
        ]
    )
    assert rc == 2
    document = json.loads(output.read_text())
    loaded = proof.load_semantic_evidence(
        document,
        advertised=True,
        expected_run_id=99,
        expected_workflow="ci",
        expected_event="pull_request",
        expected_role="pr_head",
        expected_tested_tree_sha=TREE,
        expected_subject_head_sha=HEAD,
        expected_base_sha=BASE,
    )
    assert loaded.evidence is not None
    assert loaded.evidence["status"] == "failure"
    assert loaded.evidence["authority_changed"] is True
    assert loaded.evidence["infrastructure"][0]["outcome"] == "planner_configuration_failure"


def _two_job_main_plan() -> dict:
    """Main-role plan with a sibling job, mirroring a real ci.yml pack."""
    document = _plan(role="main")
    document["eligible_jobs"] = ["job-a", "job-b"]
    document["legacy_job_count"] = 2
    document["eligible_job_count"] = 2
    document["packs"] = [
        {
            "index": index,
            "weight": 0 if index < 5 else 1,
            "jobs": [] if index < 5 else ["job-a", "job-b"],
        }
        for index in range(6)
    ]
    document["semantic_jobs"] = [
        document["semantic_jobs"][0],
        {
            "logical_job_id": "job-b",
            "pack_index": 5,
            "job_exec_sha256": JOB_SHA,
            "steps": [{"proof_id": "proof-a", "step_spec_sha256": STEP_SHA}],
        },
    ]
    document["plan_sha256"] = proof.authoritative_plan_sha256(document)
    return document


def _sibling_job(steps: list[dict]) -> dict:
    return {
        "logical_job_id": "job-b",
        "job_exec_sha256": JOB_SHA,
        "infrastructure": {"outcome": "passed"},
        "steps": steps,
    }


def _passing_step(proof_id: str, spec: str) -> dict:
    return {
        "proof_id": proof_id,
        "step_spec_sha256": spec,
        "outcome": "passed",
        "failure_signature": None,
    }


def _two_job_main_fragment(plan: dict, *, dark_outcome: str) -> dict:
    """job-a: one real failure then a unit that never ran behind it; job-b clean.

    This is the production shape of main run 32235791079 pack-2
    (``qledger-cluster-honest-ci``: one ``failed`` followed by six
    ``not_run_prior_failure`` units) beside any of its 192 clean siblings.
    """
    fragment = _fragment(role="main", plan=plan)
    fragment["jobs"][0]["steps"][0].update(
        {"outcome": "failed", "failure_signature": _signature()}
    )
    fragment["jobs"][0]["steps"][1]["outcome"] = dark_outcome
    fragment["jobs"].append(_sibling_job([_passing_step("proof-a", STEP_SHA)]))
    return fragment


@pytest.mark.parametrize(
    "dark_outcome", ["not_run_prior_failure", "timed_out", "infrastructure_blocked"]
)
def test_dark_main_unit_does_not_void_sibling_job_evidence(dark_outcome: str) -> None:
    """Regression: main run 32235791079 collapsed to ``jobs: []`` on one dark unit.

    ``ship_loop_guard._recent_main_semantic_evidence()`` reads only the aggregate
    and ``find_descendant_pass_witness()`` walks ``evidence["jobs"]``, so an empty
    jobs list pins every session in the fleet.  Whatever the classifier decides
    about the dark unit, the run must stay readable and the clean sibling must
    keep its evidence.
    """
    plan = _two_job_main_plan()
    evidence = proof.reconcile_evidence(
        plan, [_two_job_main_fragment(plan, dark_outcome=dark_outcome)]
    )
    # Representable, so the CLI never swaps it for the empty-jobs planner failure.
    assert proof.semantic_gate_verdict(evidence).clear is False
    jobs = {job["logical_job_id"]: job for job in evidence["jobs"]}
    assert set(jobs) == {"job-a", "job-b"}
    # The red job stays fully fail-closed: neither unit is a pass.
    assert proof.red_semantic_units(evidence) == frozenset(
        {("job-a", "proof-a"), ("job-a", "proof-b")}
    )
    # The clean sibling survives intact — this is the evidence the fleet needs.
    assert jobs["job-b"]["infrastructure"] == {"outcome": "passed"}
    assert jobs["job-b"]["steps"][0]["classification"] == "passed"


def test_sibling_job_pass_still_mints_a_descendant_witness_through_a_dark_unit() -> None:
    plan = _two_job_main_plan()
    evidence = proof.reconcile_evidence(
        plan, [_two_job_main_fragment(plan, dark_outcome="not_run_prior_failure")]
    )
    witness = proof.find_descendant_pass_witness(
        "job-b",
        "proof-a",
        BASE,
        [evidence],
        lambda ancestor, descendant: True,
        old_step_spec_sha=STEP_SHA,
    )
    assert witness is not None and witness.tested_tree_sha == TREE
    # The red job remains unwitnessable — widening evidence never admits a pass.
    for red_proof in ("proof-a", "proof-b"):
        assert (
            proof.find_descendant_pass_witness(
                "job-a", red_proof, BASE, [evidence], lambda *_: True
            )
            is None
        )


def test_unrepresentable_unit_is_confined_to_its_job_not_the_whole_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defense in depth: a future classifier fault costs one job, not the run.

    The rogue detector fires on a unit that would otherwise be a clean PASS, so
    this also pins that confinement is fail-closed — an unrepresentable unit is
    demoted to blocked/unknown, never kept as a pass.
    """
    plan = _two_job_main_plan()
    fragment = _fragment(role="main", plan=plan)
    fragment["jobs"].append(_sibling_job([_passing_step("proof-a", STEP_SHA)]))

    def _rogue(job_id: str, step: dict, role: str) -> str | None:
        if job_id == "job-a" and step.get("proof_id") == "proof-b":
            return "synthetic classifier fault for job-a/proof-b"
        return None

    monkeypatch.setattr(proof, "_step_representation_error", _rogue)
    evidence = proof.reconcile_evidence(plan, [fragment])
    jobs = {job["logical_job_id"]: job for job in evidence["jobs"]}
    assert jobs["job-a"]["infrastructure"]["outcome"] == "planner_configuration_failure"
    assert "job-a/proof-b" in jobs["job-a"]["infrastructure"]["detail"]
    confined = {step["proof_id"]: step for step in jobs["job-a"]["steps"]}["proof-b"]
    assert confined["outcome"] == "infrastructure_blocked"
    assert confined["classification"] == "unknown"
    # job-a/proof-a was clean and keeps its PASS; the sibling job is untouched.
    assert {s["proof_id"]: s for s in jobs["job-a"]["steps"]}["proof-a"]["classification"] == "passed"
    assert jobs["job-b"]["infrastructure"] == {"outcome": "passed"}
    assert jobs["job-b"]["steps"][0]["classification"] == "passed"
    assert proof.semantic_gate_verdict(evidence).clear is False

def _dark_step_fragment(*, plan: dict, later_outcome: str = "not_run_prior_failure") -> dict:
    """A main-role fragment whose first step failed and whose later step went
    dark behind it -- the exact production shape from main run 32231891958,
    pack-1, logical_job_id "workflow-yaml" (proof-a ~ audit_unrun_tests
    selftest which failed; proof-b ~ unrun-census discovery unit tests which
    went not_run_prior_failure behind it)."""
    return {
        "schema": proof.FRAGMENT_SCHEMA,
        **{key: plan[key] for key in (
            "workflow_run_id",
            "workflow",
            "event",
            "role",
            "tested_tree_sha",
            "subject_head_sha",
            "base_sha",
            "plan_sha256",
        )},
        "pack_index": 5,
        "infrastructure": [],
        "jobs": [
            {
                "logical_job_id": "job-a",
                "job_exec_sha256": JOB_SHA,
                "infrastructure": {"outcome": "passed"},
                "steps": [
                    {
                        "proof_id": "proof-a",
                        "step_spec_sha256": STEP_SHA,
                        "outcome": "failed",
                        "failure_signature": _signature(),
                    },
                    {
                        "proof_id": "proof-b",
                        "step_spec_sha256": OTHER_STEP_SHA,
                        "outcome": later_outcome,
                        "failure_signature": None,
                        "detail": "an earlier semantic step did not pass",
                    },
                ],
            }
        ],
    }


def test_main_dark_step_behind_earlier_failure_does_not_void_aggregate(
    tmp_path: Path,
) -> None:
    """Regression for the fleet-wide blocker: a main-role job whose first
    step failed and whose later step went dark (not_run_prior_failure) must
    still reconcile into a real, non-empty jobs list -- not get voided into
    an empty jobs list plus a planner_configuration_failure, which used to
    strip every session's ability to mint a descendant-PASS witness."""
    main_plan = _plan(role="main")
    fragment = _dark_step_fragment(plan=main_plan)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(main_plan))
    fragments_dir = tmp_path / "fragments"
    fragments_dir.mkdir()
    (fragments_dir / "pack-5.json").write_text(json.dumps(fragment))
    output = tmp_path / "final" / "ci-semantic-evidence.json"

    rc = proof.main(
        [
            "reconcile",
            "--plan",
            str(plan_path),
            "--fragments-dir",
            str(fragments_dir),
            "--output",
            str(output),
        ]
    )

    document = json.loads(output.read_text())
    assert document["jobs"], "aggregate jobs list must not be voided by a dark step"
    assert rc == 1, "genuinely blocked (main_failure present) but not an infrastructure meltdown"
    assert not any(
        row.get("outcome") == "planner_configuration_failure"
        for row in document["infrastructure"]
    )
    steps = {step["proof_id"]: step for step in document["jobs"][0]["steps"]}
    assert steps["proof-a"]["outcome"] == "failed"
    assert steps["proof-a"]["classification"] == "main_failure"
    assert steps["proof-b"]["outcome"] == "not_run_prior_failure"
    assert steps["proof-b"]["classification"] == "unknown"


def test_main_genuine_failure_is_still_classified_main_failure() -> None:
    """No regression: a main step that actually failed (not merely dark)
    must still be attributed as main_failure so real attribution logic does
    not silently start ignoring genuine main breaks."""
    main_plan = _plan(role="main")
    evidence = proof.reconcile_evidence(
        main_plan,
        [_fragment(role="main", a_outcome="failed", a_signature=_signature(), plan=main_plan)],
    )
    step = evidence["jobs"][0]["steps"][0]
    assert step["outcome"] == "failed"
    assert step["classification"] == "main_failure"
    assert proof.semantic_gate_verdict(evidence).clear is False


@pytest.mark.parametrize("outcome", ["timed_out", "infrastructure_blocked", "not_run_prior_failure"])
def test_main_non_failed_outcomes_map_to_unknown_not_main_failure(outcome: str) -> None:
    """timed_out / infrastructure_blocked / not_run_prior_failure are all
    non-"failed" outcomes on a main step; each must classify as "unknown"
    rather than "main_failure" so the aggregate validates instead of
    voiding."""
    main_plan = _plan(role="main")
    fragment = _fragment(role="main", a_outcome=outcome, plan=main_plan)
    evidence = proof.reconcile_evidence(main_plan, [fragment])
    step = evidence["jobs"][0]["steps"][0]
    assert step["outcome"] == outcome
    assert step["classification"] == "unknown"
    verdict = proof.semantic_gate_verdict(evidence)
    assert verdict.clear is False
