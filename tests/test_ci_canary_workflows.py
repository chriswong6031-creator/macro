from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def workflow(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def triggers(document: dict) -> set[str]:
    raw = document.get("on", document.get(True, {}))
    return set(raw) if isinstance(raw, dict) else {str(raw)}


def test_canaries_are_dispatch_only_and_not_merge_authority() -> None:
    for name in (
        "selfhosted-ci-canary.yml",
        "m1-runner-canary.yml",
        "merge-control-hosted-canary.yml",
    ):
        document = workflow(name)
        assert triggers(document) == {"workflow_dispatch"}
        published = {job.get("name", job_id) for job_id, job in document["jobs"].items()}
        assert not published & {
            "ci-gate",
            "fence-pack",
            "self-mod-fence",
            "capability-broker",
            "grader-manifest",
        }


def test_merge_control_hosted_canary_is_read_only_main_pinned_and_non_acting() -> None:
    document = workflow("merge-control-hosted-canary.yml")
    production = workflow("merge-on-green.yml")
    assert document["permissions"] == {"contents": "read"}
    assert set(document["jobs"]) == {"trust-gate", "hosted-environment"}
    trust = document["jobs"]["trust-gate"]
    probe = document["jobs"]["hosted-environment"]
    assert trust["runs-on"] == "ubuntu-latest"
    assert probe["runs-on"] == "ubuntu-latest"
    assert probe["needs"] == "trust-gate"
    assert "refs/heads/main" in str(trust)

    rendered = str(document)
    for forbidden in (
        "self-hosted",
        "merge-control\"]",
        "ADMIN_GH_TOKEN",
        "MERGE_TOKEN",
        "gh pr merge",
        "python3 scripts/merge_on_green.py",
    ):
        assert forbidden not in rendered

    steps = probe["steps"]
    exact_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "exact production sparse checkout"
    )
    exact = steps[exact_index]
    assert exact["uses"] == "actions/checkout@v4"
    options = exact["with"]
    assert options["filter"] == "blob:none"
    assert options["persist-credentials"] is False
    assert options["sparse-checkout-cone-mode"] is False
    assert set(str(options["sparse-checkout"]).split()) == {
        "scripts/merge_on_green.py",
        "scripts/ci_semantic_proof.py",
        "scripts/ci_authority_paths.py",
        "scripts/gh_path_filter.py",
        "scripts/run_ci_pack.py",
        ".github/workflows",
    }

    # Canary/production parity is a live contract, not duplicated prose. The canary
    # is allowed to tighten credential persistence only; the actual materialized
    # source surface and dependency bootstrap must remain byte-for-byte equivalent.
    prod_steps = production["jobs"]["sweep"]["steps"]
    prod_checkout = next(
        step for step in prod_steps if str(step.get("uses", "")).startswith("actions/checkout@")
    )
    assert exact["uses"] == prod_checkout["uses"]
    for key in ("filter", "sparse-checkout", "sparse-checkout-cone-mode"):
        assert exact["with"][key] == prod_checkout["with"][key]
    prod_bootstrap = next(step for step in prod_steps if step.get("name") == "install the yaml parser")
    canary_bootstrap = next(
        step for step in steps if step.get("name") == "exact production PyYAML bootstrap"
    )
    assert canary_bootstrap["run"] == prod_bootstrap["run"]
    parity = next(
        step for step in steps if step.get("name") == "assert canary tracks the production environment contract"
    )
    assert "merge-on-green.yml" in parity["run"]
    assert "merge-control-hosted-canary.yml" in parity["run"]
    assert "production/canary environment contract parity: OK" in parity["run"]

    production_probe_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "prove the production system-Python dependency contract"
    )
    production_probe = steps[production_probe_index]
    command = production_probe["run"]
    assert 'python3 -c "import yaml"' in command
    assert "python3 -m py_compile" in command
    assert "import scripts.merge_on_green as mog" in command
    assert "mog.main" in command

    broad_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "expand to the hosted control test surface"
    )
    broad = steps[broad_index]
    broad_options = broad["with"]
    assert broad_options["persist-credentials"] is False
    assert "/*" in broad_options["sparse-checkout"]
    assert "!/site/" in broad_options["sparse-checkout"]
    assert "!/data/" in broad_options["sparse-checkout"]

    tests_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "run existing merge-control and runner-boundary suites"
    )
    tests = steps[tests_index]["run"]
    for suite in (
        "tests/test_ci_pack.py",
        "tests/test_merge_on_green.py",
        "tests/test_runner_policy.py",
        "tests/test_ci_canary_tools.py",
        "tests/test_ci_canary_workflows.py",
    ):
        assert suite in tests

    # Negative evidence exists before Git is touched, so an early checkout/bootstrap
    # failure still leaves a receipt. PHASE 1 may advance that record but cannot accept
    # it; acceptance is reachable only after the real control suites pass. Attempt
    # identity and the first hosted-step timestamp are part of that negative receipt.
    initial_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "initialize negative canary receipt"
    )
    initial = steps[initial_index]["run"]
    assert initial_index < exact_index
    assert '"run_id": os.environ["GITHUB_RUN_ID"]' in initial
    assert '"run_attempt": os.environ["GITHUB_RUN_ATTEMPT"]' in initial
    assert '"job_started_at_observed":' in initial
    assert 'datetime.now(timezone.utc)' in initial
    assert '"phase1": "pending"' in initial
    assert '"phase2": "pending"' in initial
    assert '"production_contract_parity": False' in initial
    assert '"accepted": False' in initial

    phase1_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "record successful phase-1 environment receipt"
    )
    phase1 = steps[phase1_index]["run"]
    assert production_probe_index < phase1_index < broad_index
    assert 'receipt["phase1"] = "production_sparse_import_ok"' in phase1
    assert 'receipt["production_contract_parity"] = True' in phase1
    assert 'receipt["accepted"] = True' not in phase1

    finalize_index = next(
        index for index, step in enumerate(steps) if step.get("name") == "finalize successful canary receipt"
    )
    finalize = steps[finalize_index]
    assert tests_index < finalize_index
    assert 'receipt["phase2"] = "control_tests_ok"' in finalize["run"]
    assert 'receipt["accepted"] = True' in finalize["run"]
    upload_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("uses") == "actions/upload-artifact@v4"
        and str(step.get("with", {}).get("name", "")).startswith("merge-control-hosted-canary-")
    )
    assert finalize_index < upload_index
    assert steps[upload_index]["if"] == "always()"
    artifact_name = str(steps[upload_index]["with"]["name"])
    assert "github.run_id" in artifact_name
    assert "github.run_attempt" in artifact_name


def test_normal_ci_and_fences_remain_hosted() -> None:
    ci = workflow("ci.yml")
    assert {ci["jobs"][name]["runs-on"] for name in ("ci-plan", "ci-pack", "ci-gate")} == {"ubuntu-latest"}
    fences = workflow("fences.yml")
    for job in fences["jobs"].values():
        assert job["runs-on"] == "ubuntu-latest"


def test_selfhosted_checkout_is_cache_preceded_negotiated_and_exact_sha_verified() -> None:
    document = workflow("selfhosted-ci-canary.yml")
    steps = document["jobs"]["selfhosted-pack"]["steps"]
    prewarm = next(
        i
        for i, step in enumerate(steps)
        if step.get("name", "").startswith("prewarm exact base")
    )
    materialize = next(
        i
        for i, step in enumerate(steps)
        if step.get("name", "").startswith("materialize exact candidate")
    )
    assert prewarm < materialize
    assert "/usr/local/libexec/mastermind-ci-prewarm" in str(steps[prewarm])
    command = steps[materialize]["run"]
    assert "fetch.negotiationAlgorithm=skipping" in command
    assert "--filter=blob:none --depth=1" in command
    assert 'origin "$TESTED_SHA"' in command
    assert command.index("extraheader") < command.index("git -c credential.helper=")
    assert "GIT_TERMINAL_PROMPT=0" in command
    assert "GIT_ASKPASS=/bin/false" in command
    assert all(step.get("uses") != "actions/checkout@v4" for step in steps)
    assert "git rev-parse HEAD" in str(steps)
    assert ".git/objects/info/alternates" in str(steps)


def test_cache_negative_control_cannot_fall_through_to_checkout() -> None:
    job = workflow("selfhosted-ci-canary.yml")["jobs"]["cache-negative-control"]
    assert job["runs-on"] == ["self-hosted", "ci-linux-canary"]
    assert all(step.get("uses") != "actions/checkout@v4" for step in job["steps"])
    command = str(job["steps"][0]["run"])
    assert "intentionally-absent-cache" in command
    assert 'test "$rc" -eq 66' in command


def test_one_slot_and_three_slot_routes_cannot_consume_render() -> None:
    document = workflow("selfhosted-ci-canary.yml")
    runs_on = document["jobs"]["selfhosted-pack"]["runs-on"]
    assert "ci-linux-canary" in runs_on
    assert "ci-linux" in runs_on
    assert "render-linux" not in runs_on
    assert document["jobs"]["render-reservation-probe"]["runs-on"] == ["self-hosted", "Linux", "X64", "render-linux"]


def test_m1_canary_has_no_old_generic_route_or_checkout() -> None:
    document = workflow("m1-runner-canary.yml")
    job = document["jobs"]["m1-service-canary"]
    assert job["runs-on"] == ["self-hosted", "m1-theta"]
    assert job["needs"] == "trust-gate"
    assert document["jobs"]["trust-gate"]["runs-on"] == "ubuntu-latest"
    assert "refs/heads/main" in str(document["jobs"]["trust-gate"])
    assert not {"macstudio", "macstudio-light", "theta-m1", "codex", "render-heavy"} & set(job["runs-on"])
    assert all("uses" not in step for step in job["steps"])
    command = job["steps"][0]["run"]
    for service, runner_root, runner_name in (
        (
            "actions.runner.mastermindx-market-intelligence-macro.m1-nightly-1",
            "/Users/chriswong/actions-runner-1",
            "m1-nightly-1",
        ),
        (
            "actions.runner.mastermindx-market-intelligence-macro.m1-nightly-2",
            "/Users/chriswong/actions-runner-2",
            "m1-nightly-2",
        ),
        (
            "actions.runner.mastermindx-market-intelligence-macro.m1-light-1",
            "/Users/chriswong/actions-runner-3",
            "m1-light-1",
        ),
    ):
        assert f"{service} {runner_root} {runner_name}" in command
    assert 'launchctl print "gui/$(id -u)/$service"' in command
    assert "state = running" in command
    assert 'kill -0 "$pid"' in command
    assert 'test "$command" = "$expected_root/bin/Runner.Listener run --startuptype service"' in command
    assert '/usr/bin/plutil -extract agentName raw -o - "$expected_root/.runner"' in command
    assert 'test "$registered_name" = "$expected_name"' in command
    assert '"${listener_pids[@]}"' in command
    assert 'test "$unique_listener_count" -eq 3' in command
    assert "pgrep" not in command


def test_every_candidate_checkout_uses_the_frozen_sha_not_the_movable_merge_ref() -> None:
    document = workflow("selfhosted-ci-canary.yml")
    rendered = str(document)
    assert "steps.ref.outputs.tested_sha" in rendered
    assert rendered.count("needs.plan.outputs.tested_sha") >= 4
    checkout = next(
        step
        for step in document["jobs"]["hosted-control"]["steps"]
        if step.get("uses") == "actions/checkout@v4"
        and "tested_sha" in str(step.get("with", {}).get("ref", ""))
    )
    assert "tested_ref" not in str(checkout)
    selfhosted = str(document["jobs"]["selfhosted-pack"]["steps"])
    assert "needs.plan.outputs.tested_sha" in selfhosted
    assert "needs.plan.outputs.tested_ref" not in selfhosted


def test_contamination_probe_reuses_the_cache_without_an_origin_checkout() -> None:
    steps = workflow("selfhosted-ci-canary.yml")["jobs"]["contamination-probe"]["steps"]
    assert all(step.get("uses") != "actions/checkout@v4" for step in steps)
    detach = next(step for step in steps if step.get("name", "").startswith("detach the second"))
    assert detach["env"]["GIT_NO_LAZY_FETCH"] == "1"
    assert "needs.plan.outputs.contamination_sha" in detach["run"]
    assert "git fetch" not in detach["run"]


def test_process_contamination_probe_intentionally_abandons_and_then_rejects_a_child() -> None:
    document = workflow("selfhosted-ci-canary.yml")
    pack = str(document["jobs"]["selfhosted-pack"]["steps"])
    probe = str(document["jobs"]["contamination-probe"]["steps"])
    assert 'expected_home="$(dirname "$RUNNER_TEMP")/_home"' in pack
    assert 'test "$HOME" = "$expected_home"' in pack
    assert 'test "$HOME" = "$RUNNER_WORKSPACE/_home"' not in pack
    assert "env -u RUNNER_TRACKING_ID" in pack
    assert "mastermind-ci-leak-$GITHUB_RUN_ID" in pack
    assert "[m]astermind-ci-leak-${{ github.run_id }}" in probe


def test_red_pack_results_are_captured_instead_of_aborting_the_receipt_path() -> None:
    document = workflow("selfhosted-ci-canary.yml")
    for job_name in ("hosted-control", "selfhosted-pack"):
        command = next(
            step["run"]
            for step in document["jobs"][job_name]["steps"]
            if step.get("name") == "execute the frozen logical pack and retain its actual result"
        )
        pack = command.index("scripts/run_ci_pack.py")
        capture = command.index("pack_rc=${PIPESTATUS[0]}")
        assert command.index("set +e") < pack < capture
        assert command.index("set -e", capture) > capture


def test_canary_pins_python_3_12_13_everywhere_not_a_floating_version() -> None:
    """Mutation-lock (#6351 spec E.1): the pre-bridge canary used a floating
    ``python-version: "3.12"`` on every setup-python step. Every one must now
    pin the exact patch — gate:code / RUNNER_CONTRACT v2 parity with
    production's ci-pack setup-python step requires it (ci.yml pins 3.12.13
    for the same document-term-parser-fingerprint reason).
    """
    document = workflow("selfhosted-ci-canary.yml")
    checked = 0
    for job_id, job in document["jobs"].items():
        for step in job.get("steps", []) or []:
            if str(step.get("uses", "")).startswith("actions/setup-python@"):
                assert step["with"]["python-version"] == "3.12.13", job_id
                checked += 1
    assert checked >= 3, "expected setup-python in plan, hosted-control, and selfhosted-pack"


def test_canary_planner_and_both_consumers_declare_gate_code() -> None:
    document = workflow("selfhosted-ci-canary.yml")
    plan_run = next(
        step["run"] for step in document["jobs"]["plan"]["steps"] if step.get("id") == "plan"
    )
    assert "--gate code" in plan_run
    for job_id in ("hosted-control", "selfhosted-pack"):
        command = next(
            step["run"]
            for step in document["jobs"][job_id]["steps"]
            if step.get("name") == "execute the frozen logical pack and retain its actual result"
        )
        assert "--gate code" in command


def test_canary_consumers_use_the_published_plan_not_independent_replanning() -> None:
    """Mutation-lock: the pre-bridge consumer steps re-derived their own plan
    on every runner via ``--changed-from`` + ``--expect-plan-sha``, which
    could disagree between runners. Both consumers must load the ONE
    published ``--plan-json``, mirroring ci.yml's ci-pack step template.
    """
    document = workflow("selfhosted-ci-canary.yml")
    for job_id in ("hosted-control", "selfhosted-pack"):
        command = next(
            step["run"]
            for step in document["jobs"][job_id]["steps"]
            if step.get("name") == "execute the frozen logical pack and retain its actual result"
        )
        assert "--plan-json" in command
        assert "--changed-files-file" in command
        assert "--expect-plan-sha" in command
        assert "--expect-tested-tree-sha" in command
        assert "--expect-subject-head-sha" in command
        assert "--expect-base-sha" in command
        assert "--emit-semantic-fragment" in command
        assert "--changed-from" not in command


def test_canary_planner_passes_full_explicit_provenance_for_both_branches() -> None:
    """Mutation-lock: the pre-bridge planner passed ``--changed-from``
    unconditionally, including for pr_number=0 — an unsupported shape under
    current law. The pr_number=0 branch must never pass ``--changed-from``.
    """
    document = workflow("selfhosted-ci-canary.yml")
    plan_run = next(
        step["run"] for step in document["jobs"]["plan"]["steps"] if step.get("id") == "plan"
    )
    assert "--workflow-name infrastructure-selfhosted-ci-canary" in plan_run
    assert "--event workflow_dispatch" in plan_run
    assert "--role pr_head" in plan_run
    assert "--role main" in plan_run
    assert "--tested-tree-sha" in plan_run
    assert "--subject-head-sha" in plan_run
    assert "--base-sha" in plan_run
    assert '--changed-from "${{ steps.ref.outputs.base_sha }}"' in plan_run
    pr0_branch = plan_run.split("else", 1)[1]
    assert "--changed-from" not in pr0_branch


def test_canary_hosted_control_is_a_matrix_over_the_same_selected_packs() -> None:
    """spec item C.5: three hosted controls for three self-hosted packs."""
    document = workflow("selfhosted-ci-canary.yml")
    hosted = document["jobs"]["hosted-control"]
    assert hosted["strategy"]["matrix"] == "${{ fromJSON(needs.plan.outputs.matrix) }}"
    assert hosted["name"] == "diagnostic-hosted-control-pack-${{ matrix.pack }}"
    upload_names = {
        step["with"]["name"]
        for step in hosted["steps"]
        if step.get("uses") == "actions/upload-artifact@v4"
    }
    assert "ci-canary-hosted-${{ matrix.pack }}" in upload_names
    assert "ci-canary-hosted-fragment-${{ matrix.pack }}" in upload_names


def test_canary_compare_runs_for_both_slot_counts_over_the_selected_packs() -> None:
    """spec item C.6: strict fragment equality covers every selected pack for
    BOTH slots=1 and slots=3, not only the single-pack slots=1 shape.
    """
    document = workflow("selfhosted-ci-canary.yml")
    compare = document["jobs"]["compare"]
    assert compare["if"] == "always()"
    assert compare["strategy"]["matrix"] == "${{ fromJSON(needs.plan.outputs.matrix) }}"
    gate = next(
        step
        for step in compare["steps"]
        if step.get("name") == "require every infrastructure leg to conclude"
    )
    assert "SLOTS" in gate["env"]
    assert 'if [ "$SLOTS" = "1" ]; then' in gate["run"]
    command = next(
        step["run"]
        for step in compare["steps"]
        if step.get("name")
        == "compare logical jobs, failures, receipts, and semantic fragments"
    )
    assert "--hosted-fragment" in command
    assert "--selfhosted-fragment" in command


def test_canary_compare_uses_trusted_control_artifact_without_repo_checkout() -> None:
    """Receipt comparison must not rematerialize the multi-gigabyte repository."""
    document = workflow("selfhosted-ci-canary.yml")
    plan_steps = document["jobs"]["plan"]["steps"]
    preserve = next(
        step["run"]
        for step in plan_steps
        if step.get("name") == "preserve trusted control helpers outside the candidate workspace"
    )
    assert 'mkdir -p "$RUNNER_TEMP/ci-canary-compare-control/scripts"' in preserve
    for helper in (
        "scripts/__init__.py",
        "scripts/compare_ci_canary_receipts.py",
        "scripts/ci_semantic_proof.py",
    ):
        assert helper in preserve

    control_upload_index = next(
        index
        for index, step in enumerate(plan_steps)
        if step.get("uses") == "actions/upload-artifact@v4"
        and step.get("with", {}).get("name") == "ci-canary-compare-control"
    )
    control_upload = plan_steps[control_upload_index]
    assert control_upload["with"]["path"] == "${{ runner.temp }}/ci-canary-compare-control"
    assert control_upload["with"]["if-no-files-found"] == "error"
    candidate_checkout_index = next(
        index
        for index, step in enumerate(plan_steps)
        if step.get("name") == "checkout the exact candidate tree on hosted control"
    )
    candidate_plan_index = next(
        index
        for index, step in enumerate(plan_steps)
        if step.get("name") == "freeze the current logical plan"
    )
    assert control_upload_index < candidate_checkout_index < candidate_plan_index

    compare_steps = document["jobs"]["compare"]["steps"]
    assert all(step.get("uses") != "actions/checkout@v4" for step in compare_steps)
    control_download = next(
        step
        for step in compare_steps
        if step.get("uses") == "actions/download-artifact@v4"
        and step.get("with", {}).get("name") == "ci-canary-compare-control"
    )
    assert control_download["with"]["path"] == "${{ runner.temp }}/control"

    command = next(
        step["run"]
        for step in compare_steps
        if step.get("name")
        == "compare logical jobs, failures, receipts, and semantic fragments"
    )
    assert 'python3 "$RUNNER_TEMP/control/scripts/compare_ci_canary_receipts.py"' in command
    assert "python3 scripts/compare_ci_canary_receipts.py" not in command


def test_canary_compare_control_bundle_is_runtime_complete() -> None:
    """Reproduce the uploaded package layout and prove its entrypoint imports."""
    with tempfile.TemporaryDirectory() as temp:
        bundle = Path(temp) / "ci-canary-compare-control" / "scripts"
        bundle.mkdir(parents=True)
        for helper in (
            "__init__.py",
            "compare_ci_canary_receipts.py",
            "ci_semantic_proof.py",
        ):
            shutil.copy2(ROOT / "scripts" / helper, bundle / helper)
        completed = subprocess.run(
            [sys.executable, str(bundle / "compare_ci_canary_receipts.py"), "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
    assert completed.returncode == 0, completed.stderr
    assert "--hosted-fragment" in completed.stdout


# ── C3R-A: four-slot diagnostic interface ────────────────────────────────────
# slots=4 is a DIAGNOSTIC identity only. Its primary pack follows the existing
# ci-linux-canary label while the other three retain ci-linux; render remains
# independently reserved and a red pack must still surface after its receipt.


def _evaluate_selfhosted_route(
    expression: str,
    *,
    slots: str,
    pack: int,
    primary_pack: str,
    selected_packs: str,
) -> list[str]:
    """Evaluate the small GitHub-expression subset used by ``runs-on``.

    This exercises the shipped expression rather than a second routing helper.
    Python ``and``/``or`` has the same value-returning short-circuit behavior as
    GitHub's ``&&``/``||`` pseudo-ternary for this expression.
    """
    prefix = "${{ fromJSON("
    suffix = ") }}"
    assert expression.startswith(prefix) and expression.endswith(suffix)
    inner = expression[len(prefix) : -len(suffix)].strip()

    selected = json.loads(selected_packs)
    first_index = selected[0]["index"]
    inner = inner.replace(
        "fromJSON(needs.plan.outputs.selected_packs)[0].index",
        repr(first_index),
    )
    inner = inner.replace("needs.plan.outputs.primary_pack", repr(primary_pack))
    inner = inner.replace("inputs.slots", repr(slots))
    inner = inner.replace("matrix.pack", repr(pack))
    inner = inner.replace("&&", " and ").replace("||", " or ")
    inner = " ".join(inner.split())

    encoded = eval(  # noqa: S307 - closed expression and empty builtins
        inner,
        {"__builtins__": {}},
        {
            "fromJSON": json.loads,
            "toJSON": lambda value: json.dumps(value, separators=(",", ":")),
        },
    )
    return json.loads(encoded)


def test_canary_admits_exactly_the_one_three_and_four_slot_identities() -> None:
    document = workflow("selfhosted-ci-canary.yml")
    raw = document.get("on", document.get(True, {}))
    options = raw["workflow_dispatch"]["inputs"]["slots"]["options"]
    assert options == ["1", "3", "4"]
    assert "5" not in options and "6" not in options, "no hidden fifth CI slot"
    assert raw["workflow_dispatch"]["inputs"]["slots"]["default"] == "1"


def test_slot_routes_preserve_one_and_three_then_split_four_exactly_one_three() -> None:
    job = workflow("selfhosted-ci-canary.yml")["jobs"]["selfhosted-pack"]
    runs_on = job["runs-on"]
    selected = json.dumps(
        [{"index": 7}, {"index": 4}, {"index": 2}, {"index": 0}],
        separators=(",", ":"),
    )

    assert _evaluate_selfhosted_route(
        runs_on,
        slots="1",
        pack=7,
        primary_pack="7",
        selected_packs=selected,
    ) == ["self-hosted", "ci-linux-canary"]
    for pack in (7, 4, 2):
        assert _evaluate_selfhosted_route(
            runs_on,
            slots="3",
            pack=pack,
            primary_pack="7",
            selected_packs=selected,
        ) == ["self-hosted", "ci-linux"]

    four_routes = {
        pack: _evaluate_selfhosted_route(
            runs_on,
            slots="4",
            pack=pack,
            primary_pack="7",
            selected_packs=selected,
        )
        for pack in (7, 4, 2, 0)
    }
    assert four_routes == {
        7: ["self-hosted", "ci-linux-canary"],
        4: ["self-hosted", "ci-linux"],
        2: ["self-hosted", "ci-linux"],
        0: ["self-hosted", "ci-linux"],
    }
    assert job["strategy"]["max-parallel"] == "${{ fromJSON(inputs.slots) }}"
    assert job["strategy"]["matrix"] == "${{ fromJSON(needs.plan.outputs.matrix) }}"


@pytest.mark.parametrize(
    "primary_pack",
    ("", "not-json", '"7"', "7.0", "true", "null", "2"),
)
def test_four_slot_primary_identity_is_numeric_bound_and_fail_closed(
    primary_pack: str,
) -> None:
    """A missing, non-integer, or selector-inconsistent identity must error."""
    runs_on = workflow("selfhosted-ci-canary.yml")["jobs"]["selfhosted-pack"][
        "runs-on"
    ]
    selected = '[{"index":7},{"index":4},{"index":2},{"index":0}]'
    with pytest.raises(json.JSONDecodeError):
        _evaluate_selfhosted_route(
            runs_on,
            slots="4",
            pack=7,
            primary_pack=primary_pack,
            selected_packs=selected,
        )


def test_hosted_control_fans_out_over_every_selected_pack() -> None:
    """Four self-hosted packs need four hosted controls, or `compare` cannot
    require strict parity for every pack a slots=4 run actually selected.
    """
    hosted = workflow("selfhosted-ci-canary.yml")["jobs"]["hosted-control"]
    assert hosted["strategy"]["matrix"] == "${{ fromJSON(needs.plan.outputs.matrix) }}"
    assert hosted["runs-on"] == "ubuntu-latest"


def test_render_reservation_probe_is_preserved_at_three_and_four_slots() -> None:
    probe = workflow("selfhosted-ci-canary.yml")["jobs"]["render-reservation-probe"]
    assert probe["if"] == "inputs.slots != '1'"
    assert probe["runs-on"] == ["self-hosted", "Linux", "X64", "render-linux"]
    assert "ci-linux" not in probe["runs-on"]


def test_multi_slot_run_surfaces_red_after_preserving_the_receipt() -> None:
    """Regression: the gate previously read `inputs.slots == '3'`, so a slots=4
    run preserved its receipt and then reported success no matter what pack.rc
    held. Every multi-slot identity must surface the red.
    """
    steps = workflow("selfhosted-ci-canary.yml")["jobs"]["selfhosted-pack"]["steps"]
    upload = next(
        index
        for index, step in enumerate(steps)
        if step.get("uses") == "actions/upload-artifact@v4"
        and str(step.get("with", {}).get("name", "")).startswith("ci-canary-selfhosted-")
    )
    gate = next(
        index
        for index, step in enumerate(steps)
        if str(step.get("name", "")).startswith("surface a red pack after preserving")
    )
    assert upload < gate, "the receipt is preserved before the red is surfaced"
    assert steps[gate]["if"] == "inputs.slots != '1'"
    assert 'cat "$RUNNER_TEMP/pack.rc"' in steps[gate]["run"]
    assert "-eq 0" in steps[gate]["run"]


def test_four_slot_preflight_is_a_blocking_no_checkout_parent_envelope_gate() -> None:
    document = workflow("selfhosted-ci-canary.yml")
    preflight = document["jobs"]["four-slot-preflight"]
    assert preflight["if"] == "inputs.slots == '4'"
    assert preflight["needs"] == "plan"
    assert preflight["runs-on"] == ["self-hosted", "ci-linux-canary"]
    steps = preflight["steps"]
    assert all("checkout" not in str(step).lower() for step in steps)
    command = "\n".join(str(step.get("run", "")) for step in steps)
    assert "--require-slice" in command
    assert "--preflight-profile four-slot-canary" in command
    pack = document["jobs"]["selfhosted-pack"]
    assert "four-slot-preflight" in pack["needs"]
    assert "needs.four-slot-preflight.result == 'success'" in pack["if"]


def test_no_other_canary_job_can_race_the_four_slot_candidate() -> None:
    jobs = workflow("selfhosted-ci-canary.yml")["jobs"]
    canary_jobs = {
        job_id
        for job_id, job in jobs.items()
        if "ci-linux-canary" in str(job.get("runs-on", ""))
    }
    assert canary_jobs == {
        "four-slot-preflight",
        "selfhosted-pack",
        "cache-negative-control",
        "contamination-probe",
    }
    assert jobs["four-slot-preflight"]["if"] == "inputs.slots == '4'"
    for job_id in ("cache-negative-control", "contamination-probe"):
        assert jobs[job_id]["if"] == "inputs.slots == '1'"


def test_four_slot_keeps_all_evidence_legs_and_production_parallelism_frozen() -> None:
    document = workflow("selfhosted-ci-canary.yml")
    matrix = "${{ fromJSON(needs.plan.outputs.matrix) }}"
    for job_id in ("hosted-control", "selfhosted-pack", "compare"):
        assert document["jobs"][job_id]["strategy"]["matrix"] == matrix

    selfhosted = document["jobs"]["selfhosted-pack"]
    failure_step = next(
        step
        for step in selfhosted["steps"]
        if str(step.get("name", "")).startswith("surface a red pack")
    )
    assert failure_step["if"] == "inputs.slots != '1'"
    assert "render-linux" not in str(selfhosted["runs-on"])
    assert all(
        "pc-ci-4" not in str(job.get("runs-on", ""))
        for job in document["jobs"].values()
    )

    trusted = workflow("trusted-ci-executor.yml")["jobs"]["trusted-pack"]
    assert trusted["strategy"]["max-parallel"] == 3
