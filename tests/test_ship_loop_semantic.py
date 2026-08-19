"""Focused ship-loop contracts for canonical semantic evidence consumption."""

from __future__ import annotations

import importlib.util
import io
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "ship_loop_guard_semantic", ROOT / ".claude" / "hooks" / "ship_loop_guard.py"
)
assert SPEC and SPEC.loader
GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUARD)

HEAD = "a" * 40
BASE = "b" * 40
MERGE = "c" * 40
WITNESS_TREE = "d" * 40


def _check(name: str, conclusion: str, *, details: bool = False) -> dict:
    return {
        "name": name,
        "status": "completed",
        "conclusion": conclusion,
        "started_at": "2026-08-15T01:00:00Z",
        "details_url": "https://github.com/acme/widgets/actions/runs/77/job/9"
        if details
        else "",
        "pull_requests": [
            {"number": 9, "head": {"sha": HEAD}, "base": {"sha": BASE}}
        ],
    }


def _unit(classification: str = "inherited_base") -> SimpleNamespace:
    return SimpleNamespace(
        logical_job_id="semantic-registry",
        proof_id="registry-contract",
        classification=classification,
        outcome="failed",
        pack_index=7,
        step_spec_sha256="1" * 64,
        job_exec_sha256="2" * 64,
        failure_signature=("failed:tests/test_registry.py::test_contract",),
        detail="base never reached step" if classification == "unknown" else "same failure",
        base_sha=BASE,
        head_sha=HEAD,
    )


def _gate(
    *,
    clear: bool,
    classification: str = "inherited_base",
    infrastructure_blocking: bool = False,
) -> SimpleNamespace:
    unit = _unit(classification)
    return SimpleNamespace(
        clear=clear,
        blocking=() if clear else (unit,),
        inherited=(unit,) if clear else (),
        passed=(),
        infrastructure_blocking=infrastructure_blocking,
    )


def _loaded() -> SimpleNamespace:
    return SimpleNamespace(mode="semantic", evidence={"fixture": "head"})


def _pull() -> dict:
    return {
        "number": 9,
        "head": {"sha": HEAD},
        "base": {"ref": "main", "sha": BASE},
        "labels": [{"name": GUARD.MERGE_ON_GREEN_LABEL}],
    }


def test_unmerged_inherited_red_names_semantic_identity_not_pack(monkeypatch):
    runs = [
        _check("ci-pack-7", "failure"),
        _check("ci-gate", "success", details=True),
        _check("fence-pack", "success"),
    ]
    monkeypatch.setattr(GUARD, "_open_pull", lambda *_a: _pull())
    monkeypatch.setattr(GUARD, "_head_check_runs", lambda *_a: runs)
    monkeypatch.setattr(GUARD, "_semantic_evidence_for_head", lambda *_a, **_k: _loaded())
    monkeypatch.setattr(GUARD, "_semantic_gate", lambda _loaded: _gate(clear=True))
    monkeypatch.setattr(GUARD, "_semantic_authority_touched", lambda *_a: False)

    code, detail = GUARD._armed_pull_status(
        "acme", "widgets", "codex/example", HEAD
    )
    assert code == "unmerged"
    for phrase in (
        "logical job=semantic-registry",
        "proof id=registry-contract",
        "failure signature=",
        "base SHA=",
        "head SHA=",
        "transport pack=7",
        "ProofFreshness",
    ):
        assert phrase in detail
    assert f"base SHA={BASE}" in detail
    assert f"head SHA={HEAD}" in detail
    assert "fix ci-pack-7" not in detail.lower()


def test_main_target_split_ignores_only_inactive_pilot_authority_context() -> None:
    runs = [
        _check("ci-gate", "success"),
        _check("fence-pack", "success"),
        _check("ci-authority/main", "success"),
        _check("ci-authority/codex/merge-queue-pilot", "failure"),
    ]
    assert GUARD._split_head_runs(runs) == (
        [],
        [],
        ["ci-gate", "fence-pack", "ci-authority/main"],
    )

    active_red = [dict(run) for run in runs]
    active_red[2]["conclusion"] = "failure"
    red, pending, passed = GUARD._split_head_runs(active_red)
    assert red == ["ci-authority/main (failure)"]
    assert not pending
    assert passed == ["ci-gate", "fence-pack"]


def test_merged_head_ignores_the_inactive_pilot_context_like_its_siblings(
    monkeypatch,
) -> None:
    """`_check_ci` must agree with `_red_pairs`/`_split_head_runs` on ONE check.

    All three claim to share one definition of "not a red" — `_check_ci`'s own
    comment says so — but only two implemented the inactive-pilot exclusion.
    Measured on #5765's merged head: `_red_pairs` returned [] while `_check_ci`
    called the same head red, blocking a session whose PR had merged fully green.
    The damage is not just a false red: a non-empty `bad` ARMS the semantic
    evidence path, and a merged head cannot bind its proof base (GitHub drops
    `pull_requests` from check-runs once the PR closes), so the session was told
    "advertised semantic evidence is unusable ... does not identify the exact PR
    proof base" — proof plumbing it could not act on, for a check that is by
    design a retarget-invalidation receipt.
    """
    runs = [
        _check("ci-gate", "success"),
        _check("fence-pack", "success"),
        _check("ci-authority/main", "success"),
        _check("ci-authority/codex/merge-queue-pilot", "failure"),
    ]
    monkeypatch.setattr(GUARD, "_head_check_runs", lambda *_a: runs)

    # The sibling paths already agreed this head is clean.
    assert GUARD._red_pairs(runs) == []
    assert GUARD._split_head_runs(runs)[0] == []

    ok, detail = GUARD._check_ci(
        ROOT, "acme", "widgets", HEAD, MERGE,
        "2026-08-16T03:22:46Z", "claude/example", BASE,
    )
    assert ok, detail
    assert "merge-queue-pilot" not in detail

    # The ACTIVE context stays binding on this path too — the exclusion is one
    # literal, not a widening of the spurious-check allowlist.
    active_red = [dict(run) for run in runs]
    active_red[2]["conclusion"] = "failure"
    monkeypatch.setattr(GUARD, "_head_check_runs", lambda *_a: active_red)
    ok_red, detail_red = GUARD._check_ci(
        ROOT, "acme", "widgets", HEAD, MERGE,
        "2026-08-16T03:22:46Z", "claude/example", BASE,
    )
    assert not ok_red
    assert "ci-authority/main" in detail_red


def test_unmerged_unknown_semantic_red_says_exact_refusal(monkeypatch):
    runs = [
        _check("ci-pack-7", "failure"),
        _check("ci-gate", "failure", details=True),
    ]
    monkeypatch.setattr(GUARD, "_open_pull", lambda *_a: _pull())
    monkeypatch.setattr(GUARD, "_head_check_runs", lambda *_a: runs)
    monkeypatch.setattr(GUARD, "_semantic_evidence_for_head", lambda *_a, **_k: _loaded())
    monkeypatch.setattr(
        GUARD, "_semantic_gate", lambda _loaded: _gate(clear=False, classification="unknown")
    )
    code, detail = GUARD._armed_pull_status(
        "acme", "widgets", "codex/example", HEAD
    )
    assert code == GUARD.CI_FAILED_UNMERGED
    assert "classification=unknown" in detail
    assert "base never reached step" in detail


def test_authority_changing_pr_cannot_use_semantic_self_excuse(monkeypatch):
    runs = [
        _check("ci-pack-7", "failure"),
        _check("ci-gate", "success", details=True),
        _check("fence-pack", "success"),
    ]
    monkeypatch.setattr(GUARD, "_open_pull", lambda *_a: _pull())
    monkeypatch.setattr(GUARD, "_head_check_runs", lambda *_a: runs)
    monkeypatch.setattr(GUARD, "_semantic_evidence_for_head", lambda *_a, **_k: _loaded())
    monkeypatch.setattr(GUARD, "_semantic_gate", lambda _loaded: _gate(clear=True))
    monkeypatch.setattr(GUARD, "_semantic_authority_touched", lambda *_a: True)
    code, detail = GUARD._armed_pull_status(
        "acme", "widgets", "codex/example", HEAD
    )
    assert code == GUARD.CI_FAILED_UNMERGED
    assert "may not use candidate-era" in detail


def test_ship_loop_rename_away_keeps_previous_authority_path(monkeypatch):
    new_path = "docs/moved-merge-controller.py"
    old_path = "scripts/merge_on_green.py"
    monkeypatch.setattr(
        GUARD,
        "_get_json",
        lambda url: [
            {
                "filename": new_path,
                "previous_filename": old_path,
                "status": "renamed",
            }
        ]
        if "/pulls/9/files?" in url
        else pytest.fail(url),
    )
    checked = []

    def is_authority(path):
        checked.append(path)
        return path == old_path

    monkeypatch.setattr(GUARD, "is_ci_authority_path", is_authority)
    assert GUARD._semantic_authority_touched("acme", "widgets", 9) is True
    assert checked == [new_path, old_path]


def test_advertised_malformed_v1_is_not_legacy(monkeypatch):
    runs = [
        _check("ci-pack-7", "failure"),
        _check("ci-gate", "failure", details=True),
    ]
    monkeypatch.setattr(GUARD, "_open_pull", lambda *_a: _pull())
    monkeypatch.setattr(GUARD, "_head_check_runs", lambda *_a: runs)
    monkeypatch.setattr(
        GUARD,
        "_semantic_evidence_for_head",
        lambda *_a, **_k: (_ for _ in ()).throw(
            GUARD.semantic_proof.SemanticProofError("evidence/tree mismatch")
        ),
    )
    code, detail = GUARD._armed_pull_status(
        "acme", "widgets", "codex/example", HEAD
    )
    assert code == GUARD.CI_FAILED_UNMERGED
    assert "may not downgrade" in detail and "tree mismatch" in detail


def test_overall_red_descendant_pass_heals_frozen_unit_monotonically(
    monkeypatch, tmp_path
):
    runs = [
        _check("ci-pack-7", "failure"),
        _check("ci-gate", "failure", details=True),
    ]
    candidates = [
        {"tested_tree_sha": "e" * 40, "overall": "failure", "x": "failed-later"},
        {"tested_tree_sha": WITNESS_TREE, "overall": "failure", "x": "passed"},
    ]
    monkeypatch.setattr(GUARD, "_head_check_runs", lambda *_a: runs)
    monkeypatch.setattr(GUARD, "_semantic_evidence_for_head", lambda *_a, **_k: _loaded())
    monkeypatch.setattr(
        GUARD, "_semantic_gate", lambda _loaded: _gate(clear=False, classification="unknown")
    )
    monkeypatch.setattr(GUARD, "_recent_main_semantic_evidence", lambda *_a: candidates)
    monkeypatch.setattr(GUARD, "_run", lambda *_a, **_k: "")
    monkeypatch.setattr(
        GUARD,
        "_is_ancestor",
        lambda _root, ancestor, descendant: ancestor == MERGE and descendant == WITNESS_TREE,
    )

    def find(job, proof, merge, seen, is_ancestor, **_kwargs):
        assert (job, proof, merge) == (
            "semantic-registry",
            "registry-contract",
            MERGE,
        )
        assert seen == candidates
        assert _kwargs["old_step_spec_sha"] == "1" * 64
        # Newest later-red evidence cannot resurrect the old blocker; search any
        # ancestry-valid PASS, including one in an overall-red run.
        passed = next(item for item in seen if item.get("x") == "passed")
        assert passed["overall"] == "failure"
        assert is_ancestor(merge, passed["tested_tree_sha"])
        return SimpleNamespace(
            workflow_run_id=88,
            tested_tree_sha=passed["tested_tree_sha"],
            old_step_spec_sha="1" * 64,
            witness_step_spec_sha="3" * 64,
            contract_changed=True,
        )

    monkeypatch.setattr(GUARD.semantic_proof, "find_descendant_pass_witness", find)
    ok, detail = GUARD._check_ci(
        tmp_path,
        "acme",
        "widgets",
        HEAD,
        MERGE,
        "2026-08-15T01:30:00Z",
        "codex/example",
    )
    assert ok is True
    assert "healed by main run 88" in detail
    assert WITNESS_TREE in detail
    assert "1" * 64 in detail
    assert "3" * 64 in detail
    assert "contract_changed=true" in detail


def test_non_descendant_pass_does_not_clear_frozen_red(monkeypatch, tmp_path):
    runs = [
        _check("ci-pack-7", "failure"),
        _check("ci-gate", "failure", details=True),
    ]
    monkeypatch.setattr(GUARD, "_head_check_runs", lambda *_a: runs)
    monkeypatch.setattr(GUARD, "_semantic_evidence_for_head", lambda *_a, **_k: _loaded())
    monkeypatch.setattr(GUARD, "_semantic_gate", lambda _loaded: _gate(clear=False))
    monkeypatch.setattr(
        GUARD,
        "_recent_main_semantic_evidence",
        lambda *_a: [{"tested_tree_sha": WITNESS_TREE, "x": "passed"}],
    )
    monkeypatch.setattr(GUARD, "_run", lambda *_a, **_k: "")
    monkeypatch.setattr(GUARD, "_is_ancestor", lambda *_a: False)
    monkeypatch.setattr(
        GUARD.semantic_proof,
        "find_descendant_pass_witness",
        lambda *_args, **_kwargs: None,
    )
    ok, detail = GUARD._check_ci(
        tmp_path,
        "acme",
        "widgets",
        HEAD,
        MERGE,
        "2026-08-15T01:30:00Z",
        "codex/example",
    )
    assert ok is False
    assert "No ancestry-valid descendant PASS" in detail


def test_descendant_unit_pass_cannot_erase_frozen_infrastructure(monkeypatch, tmp_path):
    runs = [
        _check("ci-pack-7", "failure"),
        _check("ci-gate", "failure", details=True),
    ]
    loaded = SimpleNamespace(
        mode="semantic",
        evidence={
            "authority_changed": False,
            "infrastructure": [
                {"outcome": "missing_pack_fragment", "pack_indices": [7]}
            ],
        },
    )
    monkeypatch.setattr(GUARD, "_head_check_runs", lambda *_a: runs)
    monkeypatch.setattr(GUARD, "_semantic_evidence_for_head", lambda *_a, **_k: loaded)
    monkeypatch.setattr(GUARD, "_semantic_gate", lambda _loaded: _gate(clear=False))
    monkeypatch.setattr(
        GUARD,
        "_recent_main_semantic_evidence",
        lambda *_a: pytest.fail("infrastructure ambiguity attempted unit healing"),
    )
    ok, detail = GUARD._check_ci(
        tmp_path,
        "acme",
        "widgets",
        HEAD,
        MERGE,
        "2026-08-15T01:30:00Z",
        "codex/example",
    )
    assert ok is False
    assert "missing_pack_fragment" in detail
    assert "cannot erase infrastructure" in detail


def test_descendant_unit_pass_cannot_erase_frozen_job_infrastructure(
    monkeypatch, tmp_path
):
    runs = [
        _check("ci-pack-7", "failure"),
        _check("ci-gate", "failure", details=True),
    ]
    loaded = SimpleNamespace(
        mode="semantic",
        evidence={
            "authority_changed": False,
            "infrastructure": [],
            "jobs": [
                {
                    "logical_job_id": "semantic-registry",
                    "infrastructure": {
                        "outcome": "dependency_failed",
                        "detail": "pip install failed",
                    },
                }
            ],
        },
    )
    monkeypatch.setattr(GUARD, "_head_check_runs", lambda *_a: runs)
    monkeypatch.setattr(GUARD, "_semantic_evidence_for_head", lambda *_a, **_k: loaded)
    monkeypatch.setattr(
        GUARD,
        "_semantic_gate",
        lambda _loaded: _gate(
            clear=False,
            classification="unknown",
            infrastructure_blocking=True,
        ),
    )
    monkeypatch.setattr(
        GUARD,
        "_recent_main_semantic_evidence",
        lambda *_a: pytest.fail("job infrastructure attempted unit healing"),
    )

    ok, detail = GUARD._check_ci(
        tmp_path,
        "acme",
        "widgets",
        HEAD,
        MERGE,
        "2026-08-15T01:30:00Z",
        "codex/example",
    )
    assert ok is False
    assert "dependency_failed" in detail
    assert "cannot erase infrastructure" in detail


def test_green_path_performs_no_semantic_artifact_lookup(monkeypatch, tmp_path):
    monkeypatch.setattr(
        GUARD, "_head_check_runs", lambda *_a: [_check("ci-gate", "success", details=True)]
    )
    monkeypatch.setattr(
        GUARD,
        "_semantic_evidence_for_head",
        lambda *_a, **_k: pytest.fail("green path downloaded semantic evidence"),
    )
    assert GUARD._check_ci(
        tmp_path,
        "acme",
        "widgets",
        HEAD,
        MERGE,
        "2026-08-15T01:30:00Z",
        "codex/example",
    ) == (True, "")


def test_descendant_search_and_artifact_size_are_bounded():
    assert GUARD.SEMANTIC_RUN_LOOKBACK == 12
    assert GUARD.SEMANTIC_ARTIFACT_MAX_BYTES == 8 * 1024 * 1024


def test_ship_loop_binds_the_exact_ci_gate_base():
    runs = [_check("ci-gate", "failure", details=True)]
    assert GUARD._semantic_pr_base_sha(runs, HEAD, 9) == BASE
    # Absence is left to artifact selection: a genuinely pre-epoch run must keep
    # exact legacy behavior, while any present v1 still refuses without a bound base.
    assert GUARD._semantic_pr_base_sha(runs, HEAD, 10) is None


def test_ship_loop_uses_strict_shared_artifact_parser():
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(
            GUARD.SEMANTIC_ARTIFACT_FILE,
            '{"workflow":"ci","workflow":"forged"}',
        )
    with pytest.raises(
        GUARD.semantic_proof.SemanticProofError,
        match="duplicate JSON key 'workflow'",
    ):
        GUARD._semantic_json_from_archive(archive.getvalue())


def test_ship_loop_linked_red_call_delta_is_three_json_plus_one_archive(monkeypatch):
    api_calls = []
    archive_calls = []
    loader_kwargs = {}
    loaded = SimpleNamespace(
        mode="semantic", evidence={"fixture": True, "tested_tree_sha": MERGE}
    )
    artifact = {
        "name": "ci-semantic-evidence-77",
        "archive_download_url": "https://api.github.com/artifact.zip",
        "expired": False,
    }

    def get(url):
        api_calls.append(url)
        if url.endswith("/actions/runs/77"):
            return {
                "id": 77,
                "name": "ci",
                "path": ".github/workflows/ci.yml",
                "event": "pull_request",
                "head_sha": HEAD,
                "pull_requests": _check("ci-gate", "failure")["pull_requests"],
            }
        if url.endswith("/actions/runs/77/artifacts?per_page=100"):
            return {"total_count": 1, "artifacts": [artifact]}
        if url.endswith(f"/git/commits/{MERGE}"):
            return {
                "sha": MERGE,
                "parents": [{"sha": BASE}, {"sha": HEAD}],
            }
        raise AssertionError(url)

    monkeypatch.setattr(GUARD, "_get_json", get)
    monkeypatch.setattr(
        GUARD,
        "_get_artifact_bytes",
        lambda url: archive_calls.append(url) or b"archive",
    )
    monkeypatch.setattr(
        GUARD, "_semantic_json_from_archive", lambda _raw: {"fixture": True}
    )
    def load(*_args, **kwargs):
        loader_kwargs.update(kwargs)
        return loaded

    monkeypatch.setattr(GUARD.semantic_proof, "load_semantic_evidence", load)
    result = GUARD._semantic_evidence_for_head(
        "acme",
        "widgets",
        HEAD,
        check_runs=[_check("ci-gate", "failure", details=True)],
        expected_base_sha=BASE,
    )
    assert result is loaded
    assert len(api_calls) == 3
    assert not any("/workflows/ci.yml/runs" in url for url in api_calls)
    assert api_calls[-1].endswith(f"/git/commits/{MERGE}")
    assert archive_calls == ["https://api.github.com/artifact.zip"]
    assert loader_kwargs["expected_event"] == "pull_request"
    assert loader_kwargs["expected_tested_tree_sha"] is None


@pytest.mark.parametrize(
    ("commit", "message"),
    [
        (
            {"sha": "e" * 40, "parents": [{"sha": BASE}, {"sha": HEAD}]},
            "returned a different commit",
        ),
        (
            {
                "sha": MERGE,
                "parents": [{"sha": BASE}, {"sha": HEAD}, {"sha": "e" * 40}],
            },
            "not the exact two-parent PR merge",
        ),
    ],
)
def test_ship_loop_artifact_cannot_self_claim_tested_merge_tree(
    monkeypatch, commit, message
):
    artifact = {
        "name": "ci-semantic-evidence-77",
        "archive_download_url": "https://api.github.com/artifact.zip",
        "expired": False,
    }

    def get(url):
        if url.endswith("/actions/runs/77/artifacts?per_page=100"):
            return {"total_count": 1, "artifacts": [artifact]}
        if url.endswith(f"/git/commits/{MERGE}"):
            return commit
        raise AssertionError(url)

    monkeypatch.setattr(GUARD, "_get_json", get)
    monkeypatch.setattr(GUARD, "_get_artifact_bytes", lambda _url: b"archive")
    monkeypatch.setattr(GUARD, "_semantic_json_from_archive", lambda _raw: {"v": 1})
    monkeypatch.setattr(
        GUARD.semantic_proof,
        "load_semantic_evidence",
        lambda *_a, **_k: SimpleNamespace(
            mode="semantic", evidence={"tested_tree_sha": MERGE}
        ),
    )

    with pytest.raises(GUARD.semantic_proof.SemanticProofError, match=message):
        GUARD._semantic_evidence_for_run(
            "acme",
            "widgets",
            {
                "id": 77,
                "name": "ci",
                "path": ".github/workflows/ci.yml",
                "event": "pull_request",
                "head_sha": HEAD,
                "pull_requests": _check("ci-gate", "failure")["pull_requests"],
            },
            role="pr_head",
            expected_base_sha=BASE,
        )


def test_malformed_later_main_artifact_cannot_resurrect_older_valid_pass(monkeypatch):
    runs = [
        {"id": 99, "conclusion": "failure"},
        {"id": 88, "conclusion": "failure"},
    ]
    older = {"schema": "validated-older-pass"}
    monkeypatch.setattr(
        GUARD,
        "_get_json",
        lambda url: {"workflow_runs": runs}
        if "/workflows/ci.yml/runs" in url
        else pytest.fail(url),
    )

    def load(_owner, _repo, run, *, role):
        assert role == "main"
        if run["id"] == 99:
            raise GUARD.semantic_proof.SemanticProofError("malformed later artifact")
        return SimpleNamespace(mode="semantic", evidence=older)

    monkeypatch.setattr(GUARD, "_semantic_evidence_for_run", load)
    assert GUARD._recent_main_semantic_evidence("acme", "widgets") == [older]


# ---------------------------------------------------------------------------
# The other edge of the inactive-context exclusion (#5773/#5776 -> this).
#
# Excluding a check from the reds must not promote the head to PROVEN. The
# inactive context is red on every pull request in this repository, so its
# standing failure was accidentally the only thing keeping a head that proved
# NOTHING out of `_check_ci`'s cheap green return — `NON_RED_CONCLUSIONS` holds
# `skipped` and `neutral`. Measured on 65f9669f: all three shapes below returned
# `(True, "")`, releasing a session on a head with no CI verdict at all.
# ---------------------------------------------------------------------------

#: Spelled out rather than read off the guard: this suite must be able to fail
#: against a build that dropped the exclusion, and a test that reads its
#: subject's own constant cannot do that.
INACTIVE_CONTEXT = "ci-authority/codex/merge-queue-pilot"


def _merged_check(name: str, conclusion: str, *, details: bool = False) -> dict:
    """A check run on a MERGED head: `_check` minus the associations GitHub drops."""
    run = _check(name, conclusion, details=details)
    run["pull_requests"] = []
    return run


def test_the_inactive_context_literal_is_the_one_the_guard_excludes() -> None:
    assert GUARD.CI_AUTHORITY_INACTIVE_CONTEXT == INACTIVE_CONTEXT
    assert GUARD._is_non_binding_check(INACTIVE_CONTEXT)
    assert not GUARD._is_non_binding_check("ci-authority/main")


@pytest.mark.parametrize(
    "runs",
    [
        pytest.param(
            [
                _merged_check("ci-plan", "skipped"),
                _merged_check("ci-gate", "skipped"),
                _merged_check(INACTIVE_CONTEXT, "failure"),
            ],
            id="every binding check skipped",
        ),
        pytest.param(
            [
                _merged_check("some-app", "neutral"),
                _merged_check(INACTIVE_CONTEXT, "failure"),
            ],
            id="neutral only",
        ),
        pytest.param(
            [
                _merged_check(INACTIVE_CONTEXT, "failure"),
                _merged_check("Workers Builds: macro", "failure"),
            ],
            id="nothing binding at all",
        ),
    ],
)
def test_check_ci_refuses_a_merged_head_with_no_affirmative_pass(
    monkeypatch, tmp_path, runs
):
    """An unproven head must not read as green just because nothing is red."""
    monkeypatch.setattr(GUARD, "_head_check_runs", lambda *_a: runs)
    monkeypatch.setattr(
        GUARD,
        "_semantic_evidence_for_head",
        lambda *_a, **_k: pytest.fail("an unproven head must not buy evidence"),
    )
    ok, reason = GUARD._check_ci(
        tmp_path, "acme", "widgets", HEAD, MERGE, "2026-08-16T01:32:13Z", "claude/x", BASE
    )
    assert ok is False
    assert "no affirmative passing check" in reason
    # `_stop` files anything starting with "Failing" as the INTERNAL `ci_failed`
    # ladder (10 consecutive / 15 total). A merged head with no CI verdict must
    # not be the cheap external 2/3 exit, which any other wording would make it.
    assert reason.startswith("Failing")


def test_check_ci_still_greens_a_normally_merged_head(monkeypatch, tmp_path):
    """Bound on the rule above: one real success is all it asks for.

    The sweeper refuses to merge a head with no `success` at all, so every head
    reaching `_check_ci` merged has one — measured 10 of 17 on the records-only
    PR #5772. `skipped` siblings and the inactive context do not change that.
    """
    runs = [
        _merged_check("ci-gate", "success"),
        _merged_check("ci-plan", "skipped"),
        _merged_check(INACTIVE_CONTEXT, "failure"),
    ]
    monkeypatch.setattr(GUARD, "_head_check_runs", lambda *_a: runs)
    assert GUARD._check_ci(
        tmp_path, "acme", "widgets", HEAD, MERGE, "2026-08-16T01:32:13Z", "claude/x", BASE
    ) == (True, "")


def test_a_pending_head_is_still_reported_as_running_not_unproven(
    monkeypatch, tmp_path
):
    """Pending outranks the new rule: a head still working is not a head that failed."""
    runs = [
        _merged_check("ci-gate", "skipped"),
        dict(_merged_check("ci-pack-3", "success"), status="in_progress", conclusion=None),
        _merged_check(INACTIVE_CONTEXT, "failure"),
    ]
    monkeypatch.setattr(GUARD, "_head_check_runs", lambda *_a: runs)
    ok, reason = GUARD._check_ci(
        tmp_path, "acme", "widgets", HEAD, MERGE, "2026-08-16T01:32:13Z", "claude/x", BASE
    )
    assert ok is False
    assert reason.startswith("CI still running")


# ---------------------------------------------------------------------------
# The permanent-trap fence: a unit main is not eligible to report on can never
# be cleared by a descendant PASS, so it must never pin a session (PR #5936,
# 2026-08-19). Semantic eligibility is role-dependent — ci.yml plans the merge
# gate `--gate code` while `gate: data` jobs run on data-health.yml, which
# emits no main-role evidence at all — so a head planned before that split
# froze blocking units no main run will ever name again.
# ---------------------------------------------------------------------------


def _inventory(job_ids, *, artifacts=5, descendant=4):
    return GUARD.semantic_proof.MainRoleInventory(
        frozenset(job_ids), artifacts, descendant
    )


def _frozen_red_head(monkeypatch, inventory):
    runs = [
        _check("ci-pack-7", "failure"),
        _check("ci-gate", "failure", details=True),
        _check("some-other-check", "success"),
    ]
    monkeypatch.setattr(GUARD, "_head_check_runs", lambda *_a: runs)
    monkeypatch.setattr(GUARD, "_semantic_evidence_for_head", lambda *_a, **_k: _loaded())
    monkeypatch.setattr(GUARD, "_semantic_gate", lambda _loaded: _gate(clear=False))
    monkeypatch.setattr(
        GUARD, "_recent_main_semantic_evidence", lambda *_a: [{"fixture": "main"}]
    )
    monkeypatch.setattr(GUARD, "_run", lambda *_a, **_k: "")
    monkeypatch.setattr(GUARD, "_is_ancestor", lambda *_a: True)
    monkeypatch.setattr(
        GUARD.semantic_proof,
        "find_descendant_pass_witness",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        GUARD.semantic_proof,
        "main_role_job_inventory",
        lambda *_args, **_kwargs: inventory,
    )


def test_unit_main_never_plans_is_retired_not_waited_on(monkeypatch, tmp_path):
    """The measured trap: block forever on a job no main run can ever emit.

    #5936 merged clean and its Stop gate then demanded a descendant PASS for
    `house-law-registry`/`signal-contract` across seven post-merge main runs
    that structurally could not carry them.
    """
    _frozen_red_head(monkeypatch, _inventory({"some-code-job", "another-code-job"}))
    ok, detail = GUARD._check_ci(
        tmp_path,
        "acme",
        "widgets",
        HEAD,
        MERGE,
        "2026-08-15T01:30:00Z",
        "codex/example",
    )
    assert ok is True
    # Retirement is loud: the unit stays in the record by name.
    assert "semantic-registry/registry-contract" in detail
    assert "structurally unclearable" in detail
    assert "main-eligible=no" in detail


def test_main_eligible_unit_still_blocks_and_says_waiting_can_help(
    monkeypatch, tmp_path
):
    _frozen_red_head(monkeypatch, _inventory({"semantic-registry", "some-code-job"}))
    ok, detail = GUARD._check_ci(
        tmp_path,
        "acme",
        "widgets",
        HEAD,
        MERGE,
        "2026-08-15T01:30:00Z",
        "codex/example",
    )
    assert ok is False
    assert "main-eligible=yes" in detail
    assert "structurally unclearable" not in detail


def test_thin_main_inventory_never_retires_a_unit(monkeypatch, tmp_path):
    """Fail-closed: too few readable main artifacts answers `unknown`, not `no`."""
    _frozen_red_head(
        monkeypatch, _inventory({"some-code-job"}, artifacts=1, descendant=1)
    )
    ok, detail = GUARD._check_ci(
        tmp_path,
        "acme",
        "widgets",
        HEAD,
        MERGE,
        "2026-08-15T01:30:00Z",
        "codex/example",
    )
    assert ok is False
    assert "main-eligible=unknown" in detail
    assert "structurally unclearable" not in detail


def test_unreadable_inventory_leaves_the_old_refusal_intact(monkeypatch, tmp_path):
    """A raising inventory probe must not crash the gate or release the head."""

    def boom(*_args, **_kwargs):
        raise RuntimeError("artifact window unreadable")

    _frozen_red_head(monkeypatch, _inventory({"some-code-job"}))
    monkeypatch.setattr(GUARD.semantic_proof, "main_role_job_inventory", boom)
    ok, detail = GUARD._check_ci(
        tmp_path,
        "acme",
        "widgets",
        HEAD,
        MERGE,
        "2026-08-15T01:30:00Z",
        "codex/example",
    )
    assert ok is False
    assert "No ancestry-valid descendant PASS" in detail
