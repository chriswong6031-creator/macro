"""Focused consumer contracts for semantic-era merge-on-green decisions."""

from __future__ import annotations

import io
import zipfile
from types import SimpleNamespace

import pytest

import scripts.merge_on_green as MOG


HEAD = "a" * 40
BASE = "b" * 40
TREE = "c" * 40


def _check(name: str, conclusion: str, *, details: bool = False) -> dict:
    return {
        "name": name,
        "status": "completed",
        "conclusion": conclusion,
        "details_url": "https://github.com/acme/widgets/actions/runs/77/job/9"
        if details
        else "",
        "app": {"slug": "github-actions"},
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
        detail="same exact-base failure" if classification == "inherited_base" else "unknown",
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


def _loaded(label: str) -> SimpleNamespace:
    return SimpleNamespace(mode="semantic", evidence={"fixture": label})


def _pull() -> dict:
    return {
        "number": 9,
        "head": {"sha": HEAD, "ref": "codex/example"},
        "base": {"ref": "main", "sha": BASE},
        "labels": [{"name": MOG.MERGE_ON_GREEN_LABEL}],
        "state": "open",
        "draft": False,
    }


class _Fresh:
    def __init__(self, stale=(False, "current"), paths=None):
        self._stale = stale
        self._paths = list(paths or ["engine/product.py"])
        self.stale_calls = 0

    def pull_files(self, _number):
        return list(self._paths)

    def stale_for(self, _pull, _runs):
        self.stale_calls += 1
        return self._stale


def test_pack_red_is_transport_only_when_semantic_gate_is_clear(monkeypatch):
    monkeypatch.setattr(
        MOG.semantic_proof,
        "format_semantic_unit",
        lambda unit: f"{unit.logical_job_id}/{unit.proof_id}",
    )
    runs = [
        _check("ci-pack-5", "failure"),
        _check("ci-gate", "success", details=True),
        _check("fence-pack", "success"),
    ]
    assert MOG._semantic_check_verdict(runs, _gate(clear=True)) == ("clean", [])


def test_main_target_ignores_only_inactive_pilot_authority_context() -> None:
    runs = [
        _check("ci-gate", "success"),
        _check("fence-pack", "success"),
        _check("ci-authority/main", "success"),
        _check("ci-authority/codex/merge-queue-pilot", "failure"),
    ]
    assert MOG.decide_verdict(runs) == ("clean", [])

    active_red = [dict(run) for run in runs]
    active_red[2]["conclusion"] = "failure"
    verdict, names = MOG.decide_verdict(active_red)
    assert verdict == "blocked"
    assert names == ["ci-authority/main (failure)"]


def test_failing_check_names_excludes_the_inactive_context_like_decide_verdict() -> None:
    """The two halves of the sweeper must name the same reds.

    `decide_verdict` drops the inactive ci-authority context; `failing_check_names`
    did not, and that disagreement did not merely annoy — it DISABLED both
    consumers of this set (2026-08-16):

      * `_live_inherited_extras` sees the context as a non-pack "extra", so the
        live inherited-red waiver could never apply to any pull request;
      * the base-inherited-red refresh needs `bad_names <= proof.clean_names`,
        and main's proof carries JOB names — never a check-only context — so the
        containment could never hold and the mechanism that drains an armed
        backlog once main heals (#5037) was structurally dead.

    `ci-authority/main` stays binding in both, which is the whole point of the
    inactive context being a separate name from it.
    """
    runs = [
        _check("ci-pack-5", "failure"),
        _check("ci-gate", "failure"),
        _check("ci-authority/codex/merge-queue-pilot", "failure"),
        _check("ci-authority/main", "success"),
    ]
    names = MOG.failing_check_names(runs)
    assert names == {"ci-pack-5", "ci-gate"}
    # Consumer 1: nothing outside the pack/ci-gate family survives, so the live
    # inherited-red waiver is reachable at all.
    assert MOG._live_inherited_extras(names) == set()
    # Consumer 2: main's clean JOB names can now contain the whole red set.
    assert names <= {"ci-pack-5", "ci-gate", "unrun-foo"}

    active_red = [dict(run) for run in runs]
    active_red[3]["conclusion"] = "failure"
    assert "ci-authority/main" in MOG.failing_check_names(active_red)


#: Spelled out rather than read off the subject: this suite must be able to
#: fail against a build that dropped the inactive-context exclusion.
INACTIVE_CONTEXT = "ci-authority/codex/merge-queue-pilot"


def test_non_binding_check_keeps_the_active_authority_context_binding() -> None:
    assert MOG.CI_AUTHORITY_INACTIVE_CONTEXT == INACTIVE_CONTEXT
    assert MOG.is_non_binding_check(INACTIVE_CONTEXT, base_ref="main")
    assert not MOG.is_non_binding_check("ci-authority/main", base_ref="main")
    assert not MOG.is_spurious_check(INACTIVE_CONTEXT)


def test_main_pr_can_be_armed_when_only_the_inactive_pilot_context_is_red() -> None:
    """A main-target PR may receive merge-on-green despite the designed pilot red.

    ci-authority fails the unused complementary context on every PR so a
    retarget cannot reuse a success. That standing failure is not a CI
    verdict on a main PR; arming must use the same binding-check filter as
    decide_verdict, not raw "any check failed".
    """
    runs = [
        _check("ci-gate", "success"),
        _check("fence-pack", "success"),
        _check("ci-authority/main", "success"),
        _check(INACTIVE_CONTEXT, "failure"),
    ]
    assert MOG.decide_verdict(runs) == ("clean", [])
    assert MOG.can_arm_merge_on_green(runs, base_ref="main") is True


def test_real_ci_failure_still_prevents_arming_merge_on_green() -> None:
    """A binding red still refuses the label, even next to the inactive context."""
    pack_red = [
        _check("ci-gate", "success"),
        _check("ci-pack-3", "failure"),
        _check("ci-authority/main", "success"),
        _check(INACTIVE_CONTEXT, "failure"),
    ]
    assert MOG.can_arm_merge_on_green(pack_red, base_ref="main") is False
    verdict, names = MOG.decide_verdict(pack_red)
    assert verdict == "blocked"
    assert names == ["ci-pack-3 (failure)"]

    active_red = [
        _check("ci-gate", "success"),
        _check("ci-authority/main", "failure"),
        _check(INACTIVE_CONTEXT, "failure"),
    ]
    assert MOG.can_arm_merge_on_green(active_red, base_ref="main") is False
    verdict, names = MOG.decide_verdict(active_red)
    assert verdict == "blocked"
    assert names == ["ci-authority/main (failure)"]


def test_main_red_without_semantic_overlap_does_not_pause_candidate(monkeypatch):
    monkeypatch.setattr(
        MOG.semantic_proof,
        "semantic_gate_verdict",
        lambda _evidence: _gate(clear=False, infrastructure_blocking=False),
    )
    monkeypatch.setattr(
        MOG.semantic_proof,
        "red_semantic_units",
        lambda evidence: frozenset({("job-a", "proof-a")}),
    )
    monkeypatch.setattr(
        MOG.semantic_proof,
        "main_red_overlap",
        lambda main, candidate: frozenset()
        if candidate["fixture"] == "candidate-b"
        else frozenset({("job-a", "proof-a")}),
    )
    allowed, overlap, why = MOG.semantic_main_circuit_decision(
        _loaded("main-a"), _loaded("candidate-b"), ["engine/product.py"]
    )
    assert allowed is True and not overlap and why == "no semantic overlap"


def test_semantic_main_overlap_and_authority_change_both_retain_breaker(monkeypatch):
    monkeypatch.setattr(
        MOG.semantic_proof,
        "semantic_gate_verdict",
        lambda _evidence: _gate(clear=False, infrastructure_blocking=False),
    )
    monkeypatch.setattr(
        MOG.semantic_proof,
        "red_semantic_units",
        lambda _evidence: frozenset({("job-a", "proof-a")}),
    )
    monkeypatch.setattr(
        MOG.semantic_proof,
        "main_red_overlap",
        lambda *_args: frozenset({("job-a", "proof-a")}),
    )
    allowed, overlap, _why = MOG.semantic_main_circuit_decision(
        _loaded("main"), _loaded("candidate"), ["engine/product.py"]
    )
    assert allowed is False and overlap == {("job-a", "proof-a")}

    # Shared authority inventory deliberately covers every executable scripts path.
    allowed, overlap, why = MOG.semantic_main_circuit_decision(
        _loaded("main"), _loaded("candidate"), ["scripts/merge_on_green.py"]
    )
    assert allowed is False and not overlap and "authority" in why


def test_main_infrastructure_ambiguity_retains_global_breaker(monkeypatch):
    """Semantic non-overlap cannot waive unassigned runner uncertainty."""
    monkeypatch.setattr(
        MOG.semantic_proof,
        "semantic_gate_verdict",
        lambda _evidence: _gate(clear=False, infrastructure_blocking=True),
    )
    monkeypatch.setattr(
        MOG.semantic_proof,
        "red_semantic_units",
        lambda _evidence: frozenset({("job-a", "proof-a")}),
    )
    monkeypatch.setattr(
        MOG.semantic_proof,
        "main_red_overlap",
        lambda *_args: frozenset(),
    )

    allowed, overlap, why = MOG.semantic_main_circuit_decision(
        _loaded("main-with-infrastructure"),
        _loaded("candidate-b"),
        ["engine/product.py"],
    )
    assert allowed is False
    assert not overlap
    assert "infrastructure" in why


def test_job_infrastructure_is_a_nonunit_blocker() -> None:
    loaded = SimpleNamespace(
        mode="semantic",
        evidence={
            "authority_changed": False,
            "infrastructure": [],
            "jobs": [
                {
                    "logical_job_id": "job-a",
                    "infrastructure": {
                        "outcome": "dependency_failed",
                        "detail": "pip install failed",
                    },
                }
            ],
        },
    )
    gate = _gate(clear=False, infrastructure_blocking=True)
    assert MOG._semantic_has_nonunit_blocker(loaded, gate) is True
    assert "dependency_failed" in MOG._semantic_nonunit_refusal(loaded)


def test_rename_inventory_keeps_old_authority_and_surface_paths(monkeypatch):
    """Rename-away cannot erase the source path from either causal fence."""
    commit_sha = "e" * 40
    file_rows = [
        {
            "filename": "docs/moved-controller.py",
            "previous_filename": "scripts/merge_on_green.py",
            "status": "renamed",
        },
        {
            "filename": "docs/moved-engine.py",
            "previous_filename": "engine/model.py",
            "status": "renamed",
        },
        # Duplicate identities remain one stable inventory even across API rows.
        {
            "filename": "docs/moved-engine.py",
            "previous_filename": "engine/model.py",
            "status": "renamed",
        },
    ]

    def request(_method, url, _token, *_a, **_k):
        if "/pulls/9/files?" in url:
            return 200, file_rows
        if url.endswith(f"/commits/{commit_sha}"):
            return 200, {"files": file_rows}
        raise AssertionError(url)

    monkeypatch.setattr(MOG, "_request", request)
    freshness = MOG.ProofFreshness(
        "acme/widgets",
        "read",
        [{"workflow": "ci.yml", "patterns": ["engine/**"]}],
        [{"sha": commit_sha, "message": "rename guarded files"}],
    )
    expected = [
        "docs/moved-controller.py",
        "scripts/merge_on_green.py",
        "docs/moved-engine.py",
        "engine/model.py",
    ]

    assert freshness.pull_files(9) == expected
    assert freshness.surface_of(9) == {"engine/**"}
    assert MOG._touches_semantic_authority(freshness.pull_files(9)) is True
    assert freshness.files_of(commit_sha) == (expected, False)
    assert MOG._semantic_pull_paths("acme/widgets", 9, "read") == expected


def test_semantic_clear_still_runs_proof_freshness_and_reproves(monkeypatch):
    runs = [
        _check("ci-pack-5", "failure"),
        _check("ci-gate", "success", details=True),
        _check("fence-pack", "success"),
    ]
    fresh = _Fresh(stale=(True, "newer main changed the tested surface"))
    monkeypatch.setattr(MOG, "head_check_runs", lambda *_a: runs)
    monkeypatch.setattr(MOG, "_semantic_gate", lambda _loaded: _gate(clear=True))
    monkeypatch.setattr(
        MOG.semantic_proof,
        "format_semantic_unit",
        lambda unit: f"{unit.logical_job_id}/{unit.proof_id}",
    )
    calls = []
    monkeypatch.setattr(
        MOG,
        "reprove",
        lambda repo, pull, reason, read, write, budget: calls.append(reason) or "rebased",
    )
    verdict = MOG.sweep_pull(
        "acme/widgets",
        _pull(),
        "read",
        "write",
        fresh,
        semantic_evidence=_loaded("candidate"),
    )
    assert verdict == "rebased"
    assert fresh.stale_calls == 1
    assert calls == ["newer main changed the tested surface"]


def test_advertised_malformed_v1_fails_closed_instead_of_legacy(monkeypatch):
    runs = [
        _check("ci-pack-5", "failure"),
        _check("ci-gate", "failure", details=True),
        _check("fence-pack", "success"),
    ]
    monkeypatch.setattr(MOG, "head_check_runs", lambda *_a: runs)
    monkeypatch.setattr(
        MOG,
        "semantic_evidence_for_head",
        lambda *_a, **_k: (_ for _ in ()).throw(
            MOG.semantic_proof.SemanticProofError("tree mismatch")
        ),
    )
    monkeypatch.setattr(MOG, "live_authorized_pull", lambda *_a, **_k: (_pull(), "ok"))
    comments = []
    monkeypatch.setattr(
        MOG,
        "mark_blocked",
        lambda _repo, _pull, message, _token: comments.append(message) or True,
    )
    verdict = MOG.sweep_pull(
        "acme/widgets", _pull(), "read", "write", _Fresh()
    )
    assert verdict == "blocked"
    assert "may not downgrade" in comments[0]
    assert "tree mismatch" in comments[0]


def test_mark_only_agrees_that_inherited_pack_red_is_not_own_failure(monkeypatch, capsys):
    runs = [
        _check("ci-pack-5", "failure"),
        _check("ci-gate", "success", details=True),
        _check("fence-pack", "success"),
    ]
    monkeypatch.setattr(MOG, "labeled_pulls", lambda *_a: [_pull()])
    monkeypatch.setattr(MOG, "head_check_runs", lambda *_a: runs)
    monkeypatch.setattr(MOG, "semantic_evidence_for_head", lambda *_a, **_k: _loaded("head"))
    monkeypatch.setattr(MOG, "_semantic_gate", lambda _loaded: _gate(clear=True))
    monkeypatch.setattr(MOG, "_semantic_pull_paths", lambda *_a: ["engine/product.py"])
    monkeypatch.setattr(
        MOG.semantic_proof,
        "format_semantic_unit",
        lambda unit: f"{unit.logical_job_id}/{unit.proof_id}",
    )
    monkeypatch.setattr(
        MOG, "mark_blocked", lambda *_a, **_k: pytest.fail("inherited red was marked")
    )
    wakes = []
    monkeypatch.setattr(
        MOG,
        "ensure_self_wake",
        lambda *args, **_kwargs: wakes.append(args[-1]) or "dispatched",
    )
    assert MOG.mark_only_pass(
        "acme/widgets", "read", "write", HEAD, current_run_id="99"
    ) == 0
    assert "semantic proof is clear" in capsys.readouterr().out
    assert wakes and "semantic-clear" in wakes[0]


def test_legacy_red_without_concrete_gate_run_does_not_fetch_artifact(monkeypatch):
    runs = [_check("ci-pack-2", "failure"), _check("fence-pack", "success")]
    assert MOG._head_can_advertise_semantic_evidence(runs) is False
    monkeypatch.setattr(
        MOG,
        "semantic_evidence_for_head",
        lambda *_a, **_k: pytest.fail("legacy head attempted semantic artifact lookup"),
    )
    # The pure legacy verdict remains exactly the existing pack-name verdict.
    verdict, names = MOG.decide_verdict(runs)
    assert verdict == "blocked" and "ci-pack-2 (failure)" in names


def test_green_sweeper_head_performs_zero_semantic_artifact_calls(monkeypatch):
    runs = [
        _check("ci-pack-5", "success"),
        _check("ci-gate", "success", details=True),
        _check("fence-pack", "success"),
    ]
    fresh = _Fresh(stale=(True, "newer main requires ordinary reproof"))
    monkeypatch.setattr(
        MOG,
        "semantic_evidence_for_head",
        lambda *_a, **_k: pytest.fail("green sweeper head downloaded semantic evidence"),
    )
    monkeypatch.setattr(MOG, "reprove", lambda *_a, **_k: "rebased")
    assert MOG.sweep_pull(
        "acme/widgets",
        _pull(),
        "read",
        "write",
        fresh,
        check_runs=runs,
    ) == "rebased"
    assert fresh.stale_calls == 1


def test_concrete_historical_run_with_no_v1_uses_exact_legacy_block(monkeypatch):
    runs = [
        _check("ci-pack-2", "failure"),
        _check("ci-gate", "failure", details=True),
        _check("fence-pack", "success"),
    ]
    monkeypatch.setattr(MOG, "head_check_runs", lambda *_a: runs)
    monkeypatch.setattr(
        MOG,
        "semantic_evidence_for_head",
        lambda *_a, **_k: SimpleNamespace(mode="legacy_absent", evidence=None),
    )
    monkeypatch.setattr(MOG, "live_inherited_red", lambda *_a, **_k: None)
    monkeypatch.setattr(MOG, "live_authorized_pull", lambda *_a, **_k: (_pull(), "ok"))
    comments = []
    monkeypatch.setattr(
        MOG,
        "mark_blocked",
        lambda _repo, _pull, message, _token: comments.append(message) or True,
    )
    verdict = MOG.sweep_pull(
        "acme/widgets", _pull(), "read", "write", _Fresh()
    )
    assert verdict == "blocked"
    assert "ci-pack-2 (failure)" in comments[0]
    assert "semantic proof refusal" not in comments[0]


def test_duplicate_advertised_artifacts_refuse(monkeypatch):
    artifact = {
        "name": "ci-semantic-evidence-77",
        "archive_download_url": "https://api.github.com/artifact.zip",
        "expired": False,
    }
    monkeypatch.setattr(
        MOG,
        "_request",
        lambda *_a, **_k: (200, {"total_count": 2, "artifacts": [artifact, artifact]}),
    )
    with pytest.raises(MOG.semantic_proof.SemanticProofError, match="2 semantic artifacts"):
        MOG._semantic_evidence_for_run(
            "acme/widgets",
            {
                "id": 77,
                "name": "ci",
                "path": ".github/workflows/ci.yml",
                "event": "pull_request",
                "head_sha": HEAD,
            },
            "read",
            role="pr_head",
        )


def test_semantic_era_tree_with_missing_final_artifact_refuses(monkeypatch):
    def request(_method, url, _token, *_a, **_k):
        if "/artifacts" in url:
            return 200, {"total_count": 0, "artifacts": []}
        if "/contents/scripts/ci_semantic_proof.py" in url:
            return 200, {"sha": "marker"}
        raise AssertionError(url)

    monkeypatch.setattr(MOG, "_request", request)
    with pytest.raises(MOG.semantic_proof.SemanticProofError):
        MOG._semantic_evidence_for_run(
            "acme/widgets",
            {
                "id": 77,
                "name": "ci",
                "path": ".github/workflows/ci.yml",
                "event": "pull_request",
                "head_sha": HEAD,
            },
            "read",
            role="pr_head",
        )


def test_pre_epoch_run_with_no_artifact_is_legacy_absent(monkeypatch):
    def request(_method, url, _token, *_a, **_k):
        if "/artifacts" in url:
            return 200, {"total_count": 0, "artifacts": []}
        if "/contents/scripts/ci_semantic_proof.py" in url:
            return 404, {"message": "not found"}
        raise AssertionError(url)

    monkeypatch.setattr(MOG, "_request", request)
    loaded = MOG._semantic_evidence_for_run(
        "acme/widgets",
        {
            "id": 77,
            "name": "ci",
            "path": ".github/workflows/ci.yml",
            "event": "pull_request",
            "head_sha": HEAD,
        },
        "read",
        role="pr_head",
    )
    assert loaded.mode == "legacy_absent"


def test_linked_gate_skips_the_extra_workflow_run_listing(monkeypatch):
    calls = []
    api_calls = []

    def load(repo, run, token, *, role, expected_base_sha=None):
        calls.append((repo, run, token, role, expected_base_sha))
        return SimpleNamespace(mode="legacy_absent", evidence=None)

    monkeypatch.setattr(MOG, "_semantic_evidence_for_run", load)

    def request(_method, url, _token, *_a, **_k):
        api_calls.append(url)
        assert url.endswith("/actions/runs/77")
        return 200, {
            "id": 77,
            "name": "ci",
            "path": ".github/workflows/ci.yml",
            "event": "pull_request",
            "head_sha": HEAD,
            "pull_requests": _check("ci-gate", "failure")["pull_requests"],
        }

    monkeypatch.setattr(
        MOG,
        "_request",
        request,
    )
    loaded = MOG.semantic_evidence_for_head(
        "acme/widgets",
        HEAD,
        "read",
        check_runs=[_check("ci-gate", "failure", details=True)],
        expected_base_sha=BASE,
    )
    assert loaded.mode == "legacy_absent"
    assert calls[0][1]["id"] == 77
    assert calls[0][4] == BASE
    assert len(api_calls) == 1
    assert not any("/workflows/ci.yml/runs" in url for url in api_calls)


def test_linked_red_artifact_call_delta_is_three_json_plus_one_archive(monkeypatch):
    api_calls = []
    archive_calls = []
    loader_kwargs = {}
    artifact = {
        "name": "ci-semantic-evidence-77",
        "archive_download_url": "https://api.github.com/artifact.zip",
        "expired": False,
    }

    def request(_method, url, _token, *_a, **_k):
        api_calls.append(url)
        if url.endswith("/actions/runs/77"):
            return 200, {
                "id": 77,
                "name": "ci",
                "path": ".github/workflows/ci.yml",
                "event": "pull_request",
                "head_sha": HEAD,
                "pull_requests": _check("ci-gate", "failure")["pull_requests"],
            }
        if url.endswith("/actions/runs/77/artifacts?per_page=100"):
            return 200, {"total_count": 1, "artifacts": [artifact]}
        if url.endswith(f"/git/commits/{TREE}"):
            return 200, {
                "sha": TREE,
                "parents": [{"sha": BASE}, {"sha": HEAD}],
            }
        raise AssertionError(url)

    monkeypatch.setattr(MOG, "_request", request)
    monkeypatch.setattr(
        MOG,
        "_download_semantic_artifact",
        lambda url, token: archive_calls.append((url, token)) or b"archive",
    )
    monkeypatch.setattr(MOG, "_semantic_json_from_archive", lambda _raw: {"fixture": True})
    expected = SimpleNamespace(
        mode="semantic", evidence={"fixture": True, "tested_tree_sha": TREE}
    )
    def load(*_args, **kwargs):
        loader_kwargs.update(kwargs)
        return expected

    monkeypatch.setattr(MOG.semantic_proof, "load_semantic_evidence", load)
    assert MOG.semantic_evidence_for_head(
        "acme/widgets",
        HEAD,
        "read",
        check_runs=[_check("ci-gate", "failure", details=True)],
        expected_base_sha=BASE,
    ) is expected
    assert len(api_calls) == 3
    assert not any("/workflows/ci.yml/runs" in url for url in api_calls)
    assert api_calls[-1].endswith(f"/git/commits/{TREE}")
    assert archive_calls == [("https://api.github.com/artifact.zip", "read")]
    assert loader_kwargs["expected_event"] == "pull_request"
    assert loader_kwargs["expected_tested_tree_sha"] is None


@pytest.mark.parametrize(
    ("commit", "message"),
    [
        (
            {"sha": "d" * 40, "parents": [{"sha": BASE}, {"sha": HEAD}]},
            "returned a different commit",
        ),
        (
            {"sha": TREE, "parents": [{"sha": HEAD}, {"sha": BASE}]},
            "not the exact two-parent PR merge",
        ),
    ],
)
def test_pr_artifact_cannot_self_claim_tested_merge_tree(
    monkeypatch, commit, message
):
    artifact = {
        "name": "ci-semantic-evidence-77",
        "archive_download_url": "https://api.github.com/artifact.zip",
        "expired": False,
    }

    def request(_method, url, _token, *_a, **_k):
        if url.endswith("/actions/runs/77/artifacts?per_page=100"):
            return 200, {"total_count": 1, "artifacts": [artifact]}
        if url.endswith(f"/git/commits/{TREE}"):
            return 200, commit
        raise AssertionError(url)

    monkeypatch.setattr(MOG, "_request", request)
    monkeypatch.setattr(MOG, "_download_semantic_artifact", lambda *_a: b"archive")
    monkeypatch.setattr(MOG, "_semantic_json_from_archive", lambda _raw: {"v": 1})
    monkeypatch.setattr(
        MOG.semantic_proof,
        "load_semantic_evidence",
        lambda *_a, **_k: SimpleNamespace(
            mode="semantic", evidence={"tested_tree_sha": TREE}
        ),
    )

    with pytest.raises(MOG.semantic_proof.SemanticProofError, match=message):
        MOG._semantic_evidence_for_run(
            "acme/widgets",
            {
                "id": 77,
                "name": "ci",
                "path": ".github/workflows/ci.yml",
                "event": "pull_request",
                "head_sha": HEAD,
                "pull_requests": _check("ci-gate", "failure")["pull_requests"],
            },
            "read",
            role="pr_head",
            expected_base_sha=BASE,
        )


def test_deleted_head_marker_cannot_hide_semantic_era_base(monkeypatch):
    seen_refs = []

    def request(_method, url, _token, *_a, **_k):
        if "/artifacts" in url:
            return 200, {"total_count": 0, "artifacts": []}
        if "/contents/scripts/ci_semantic_proof.py" in url:
            ref = url.rsplit("ref=", 1)[-1]
            seen_refs.append(ref)
            return (200, {"sha": "marker"}) if ref == BASE else (404, {})
        raise AssertionError(url)

    monkeypatch.setattr(MOG, "_request", request)
    with pytest.raises(
        MOG.semantic_proof.SemanticProofError,
        match="semantic-era run is missing",
    ):
        MOG._semantic_evidence_for_run(
            "acme/widgets",
            {
                "id": 77,
                "name": "ci",
                "path": ".github/workflows/ci.yml",
                "event": "pull_request",
                "head_sha": HEAD,
                "pull_requests": [],
            },
            "read",
            role="pr_head",
            expected_base_sha=BASE,
        )
    assert seen_refs == [HEAD, BASE]


def test_pr_artifact_refuses_base_metadata_disagreement(monkeypatch):
    artifact = {
        "name": "ci-semantic-evidence-77",
        "archive_download_url": "https://api.github.com/artifact.zip",
        "expired": False,
    }
    monkeypatch.setattr(
        MOG,
        "_request",
        lambda *_a, **_k: (200, {"total_count": 1, "artifacts": [artifact]}),
    )
    monkeypatch.setattr(
        MOG,
        "_download_semantic_artifact",
        lambda *_a, **_k: pytest.fail("base mismatch must refuse before download"),
    )
    with pytest.raises(
        MOG.semantic_proof.SemanticProofError,
        match="base metadata disagrees",
    ):
        MOG._semantic_evidence_for_run(
            "acme/widgets",
            {
                "id": 77,
                "name": "ci",
                "path": ".github/workflows/ci.yml",
                "event": "pull_request",
                "head_sha": HEAD,
                "pull_requests": [
                    {
                        "number": 9,
                        "head": {"sha": HEAD},
                        "base": {"sha": "c" * 40},
                    }
                ],
            },
            "read",
            role="pr_head",
            expected_base_sha=BASE,
        )


def test_artifact_json_duplicate_keys_are_rejected_by_shared_parser():
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(
            MOG.SEMANTIC_ARTIFACT_FILE,
            '{"schema":"ci.semantic_evidence.v1","schema":"shadow"}',
        )
    with pytest.raises(
        MOG.semantic_proof.SemanticProofError,
        match="duplicate JSON key 'schema'",
    ):
        MOG._semantic_json_from_archive(archive.getvalue())


@pytest.mark.parametrize(
    ("name", "path", "event", "message"),
    [
        (
            "forged-ci",
            ".github/workflows/ci.yml",
            "pull_request",
            "not the ci workflow",
        ),
        (
            "ci",
            ".github/workflows/forged.yml",
            "pull_request",
            "not from .github/workflows/ci.yml",
        ),
        (
            "ci",
            ".github/workflows/ci.yml",
            "workflow_dispatch",
            "event does not match semantic role",
        ),
    ],
)
def test_pr_artifact_binds_rest_workflow_identity(name, path, event, message):
    with pytest.raises(MOG.semantic_proof.SemanticProofError, match=message):
        MOG._semantic_evidence_for_run(
            "acme/widgets",
            {
                "id": 77,
                "name": name,
                "path": path,
                "event": event,
                "head_sha": HEAD,
                "pull_requests": _check("ci-gate", "failure")["pull_requests"],
            },
            "read",
            role="pr_head",
            expected_base_sha=BASE,
        )


def test_red_breaker_orders_semantic_main_without_blocked_names(monkeypatch):
    """The producer is fed by breaker state, not a post-sweep blocked-name set."""
    calls = []

    def request(method, url, token, payload=None, **_kwargs):
        calls.append((method, url, token, payload))
        if method == "GET" and "/workflows/ci.yml/runs?" in url:
            return 200, {"workflow_runs": []}
        if method == "GET" and url.endswith("/git/ref/heads/main"):
            return 200, {"object": {"sha": HEAD}}
        if method == "POST" and url.endswith("/workflows/ci.yml/dispatches"):
            return 204, {}
        raise AssertionError((method, url))

    monkeypatch.setattr(MOG, "_request", request)
    monkeypatch.setattr(MOG, "_annotate", lambda *_a, **_k: None)

    result = MOG.ensure_semantic_main_evidence(
        "acme/widgets",
        "write",
        baseline_state="red",
        semantic_main_available=False,
        gap="no post-cutover semantic main artifact",
    )

    assert result == f"dispatched for {HEAD}"
    assert len(calls) == 3
    assert calls[-1] == (
        "POST",
        "https://api.github.com/repos/acme/widgets/actions/workflows/ci.yml/dispatches",
        "write",
        {"ref": "main", "inputs": {"expected_sha": HEAD}},
    )


def test_semantic_main_producer_does_not_duplicate_pending_run(monkeypatch):
    calls = []

    def request(method, url, token, payload=None, **_kwargs):
        calls.append((method, url, token, payload))
        return 200, {
            "workflow_runs": [
                {
                    "id": 88,
                    "status": "in_progress",
                    "head_sha": HEAD,
                    "created_at": "2026-08-15T00:00:00Z",
                }
            ]
        }

    monkeypatch.setattr(MOG, "_request", request)

    result = MOG.ensure_semantic_main_evidence(
        "acme/widgets",
        "write",
        baseline_state="red",
        semantic_main_available=False,
    )

    assert result == "skipped (a semantic-main proof is already in_progress)"
    assert len(calls) == 1
    assert calls[0][0] == "GET"


def test_semantic_main_dispatch_binds_literal_observed_sha(monkeypatch):
    """A stale historical run never supplies the dispatch identity."""
    stale_sha = "c" * 40
    calls = []

    def request(method, url, token, payload=None, **_kwargs):
        calls.append((method, url, token, payload))
        if method == "GET" and "/workflows/ci.yml/runs?" in url:
            return 200, {
                "workflow_runs": [
                    {
                        "id": 87,
                        "status": "completed",
                        "head_sha": stale_sha,
                        "created_at": "2020-01-01T00:00:00Z",
                    }
                ]
            }
        if method == "GET" and url.endswith("/git/ref/heads/main"):
            return 200, {"object": {"sha": HEAD}}
        if method == "POST" and url.endswith("/workflows/ci.yml/dispatches"):
            return 204, {}
        raise AssertionError((method, url))

    monkeypatch.setattr(MOG, "_request", request)
    monkeypatch.setattr(MOG, "_annotate", lambda *_a, **_k: None)

    result = MOG.ensure_semantic_main_evidence(
        "acme/widgets",
        "write",
        baseline_state="red",
        semantic_main_available=False,
    )

    assert result == f"dispatched for {HEAD}"
    assert calls[-1][3] == {"ref": "main", "inputs": {"expected_sha": HEAD}}
    assert stale_sha not in str(calls[-1][3])


def test_semantic_main_lookup_failure_is_fail_closed(monkeypatch):
    calls = []

    def request(method, url, token, payload=None, **_kwargs):
        calls.append((method, url, token, payload))
        return 503, {"message": "unavailable"}

    warnings = []
    monkeypatch.setattr(MOG, "_request", request)
    monkeypatch.setattr(
        MOG,
        "_annotate",
        lambda level, title, message: warnings.append((level, title, message)),
    )

    result = MOG.ensure_semantic_main_evidence(
        "acme/widgets",
        "write",
        baseline_state="red",
        semantic_main_available=False,
    )

    assert result == "skipped (newest semantic-main run lookup HTTP 503)"
    assert len(calls) == 1
    assert warnings and "breaker stays closed" in warnings[0][2]


def test_semantic_main_malformed_run_listing_is_fail_closed(monkeypatch):
    calls = []

    def request(method, url, token, payload=None, **_kwargs):
        calls.append((method, url, token, payload))
        return 200, {"workflow_runs": {"forged": "not-a-list"}}

    warnings = []
    monkeypatch.setattr(MOG, "_request", request)
    monkeypatch.setattr(
        MOG,
        "_annotate",
        lambda level, title, message: warnings.append((level, title, message)),
    )

    result = MOG.ensure_semantic_main_evidence(
        "acme/widgets",
        "write",
        baseline_state="red",
        semantic_main_available=False,
    )

    assert result == "skipped (newest semantic-main run listing is malformed)"
    assert len(calls) == 1
    assert warnings and "breaker stays closed" in warnings[0][2]


def test_semantic_main_dispatch_failure_is_fail_closed(monkeypatch):
    calls = []

    def request(method, url, token, payload=None, **_kwargs):
        calls.append((method, url, token, payload))
        if method == "GET" and "/workflows/ci.yml/runs?" in url:
            return 200, {"workflow_runs": []}
        if method == "GET" and url.endswith("/git/ref/heads/main"):
            return 200, {"object": {"sha": HEAD}}
        if method == "POST" and url.endswith("/workflows/ci.yml/dispatches"):
            return 500, {"message": "dispatch unavailable"}
        raise AssertionError((method, url))

    warnings = []
    monkeypatch.setattr(MOG, "_request", request)
    monkeypatch.setattr(
        MOG,
        "_annotate",
        lambda level, title, message: warnings.append((level, title, message)),
    )

    result = MOG.ensure_semantic_main_evidence(
        "acme/widgets",
        "write",
        baseline_state="red",
        semantic_main_available=False,
    )

    assert result == "dispatch failed (HTTP 500)"
    assert len(calls) == 3
    assert warnings and "breaker stays closed" in warnings[0][2]


@pytest.mark.parametrize("baseline_state", ["green", "unknown"])
def test_semantic_main_producer_is_zero_cost_off_red(monkeypatch, baseline_state):
    monkeypatch.setattr(
        MOG,
        "_request",
        lambda *_a, **_k: pytest.fail("non-red breaker called semantic producer API"),
    )
    assert MOG.ensure_semantic_main_evidence(
        "acme/widgets",
        "write",
        baseline_state=baseline_state,
        semantic_main_available=False,
    ).startswith("not needed")


def test_semantic_main_producer_is_zero_cost_when_evidence_exists(monkeypatch):
    monkeypatch.setattr(
        MOG,
        "_request",
        lambda *_a, **_k: pytest.fail("usable semantic main proof triggered dispatch"),
    )
    assert MOG.ensure_semantic_main_evidence(
        "acme/widgets",
        "write",
        baseline_state="red",
        semantic_main_available=True,
    ) == "not needed (current semantic main evidence is available)"
