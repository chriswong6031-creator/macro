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


def test_selfhosted_checkout_is_cache_preceded_and_exact_sha_verified() -> None:
    document = workflow("selfhosted-ci-canary.yml")
    steps = document["jobs"]["selfhosted-pack"]["steps"]
    prewarm = next(
        i
        for i, step in enumerate(steps)
        if step.get("name", "").startswith("prewarm exact base")
    )
    checkout = next(i for i, step in enumerate(steps) if step.get("uses") == "actions/checkout@v4")
    assert prewarm < checkout
    assert "/usr/local/libexec/mastermind-ci-prewarm" in str(steps[prewarm])
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
    assert "pgrep -f 'Runner.Listener' | wc -l" in command
    assert "pgrep -fc" not in command


def test_every_candidate_checkout_uses_the_frozen_sha_not_the_movable_merge_ref() -> None:
    document = workflow("selfhosted-ci-canary.yml")
    rendered = str(document)
    assert "steps.ref.outputs.tested_sha" in rendered
    assert rendered.count("needs.plan.outputs.tested_sha") >= 4
    for job_name in ("hosted-control", "selfhosted-pack"):
        checkout = next(
            step
            for step in document["jobs"][job_name]["steps"]
            if step.get("uses") == "actions/checkout@v4"
            and "tested_sha" in str(step.get("with", {}).get("ref", ""))
        )
        assert "tested_ref" not in str(checkout)


def test_process_contamination_probe_intentionally_abandons_and_then_rejects_a_child() -> None:
    document = workflow("selfhosted-ci-canary.yml")
    pack = str(document["jobs"]["selfhosted-pack"]["steps"])
    probe = str(document["jobs"]["contamination-probe"]["steps"])
    assert "env -u RUNNER_TRACKING_ID" in pack
    assert "mastermind-ci-leak-$GITHUB_RUN_ID" in pack
    assert "[m]astermind-ci-leak-${{ github.run_id }}" in probe
