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
    job = workflow("m1-runner-canary.yml")["jobs"]["m1-service-canary"]
    assert job["runs-on"] == ["self-hosted", "m1-theta"]
    assert not {"macstudio", "macstudio-light", "theta-m1", "codex", "render-heavy"} & set(job["runs-on"])
    assert all("uses" not in step for step in job["steps"])
