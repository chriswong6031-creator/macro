from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def workflow(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def triggers(document: dict) -> set[str]:
    raw = document.get("on", document.get(True, {}))
    return set(raw) if isinstance(raw, dict) else {str(raw)}


def test_canaries_are_dispatch_only_and_not_merge_authority() -> None:
    for name in ("selfhosted-ci-canary.yml", "m1-runner-canary.yml"):
        document = workflow(name)
        assert triggers(document) == {"workflow_dispatch"}
        published = {job.get("name", job_id) for job_id, job in document["jobs"].items()}
        assert not published & {"ci-gate", "fence-pack", "self-mod-fence", "capability-broker", "grader-manifest"}


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
    assert "env -u RUNNER_TRACKING_ID" in pack
    assert "mastermind-ci-leak-$GITHUB_RUN_ID" in pack
    assert "[m]astermind-ci-leak-${{ github.run_id }}" in probe
