"""Keep self-hosted render checkouts from accumulating generated-site history."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "render.yml"


def _steps() -> list[dict]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return workflow["jobs"]["render"]["steps"]


def test_oversized_checkout_is_bounded_before_checkout_runs():
    steps = _steps()
    bound_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "bound persisted render checkout"
    )
    checkout_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("uses") == "actions/checkout@v4"
    )
    assert bound_index < checkout_index

    script = steps[bound_index]["run"]
    assert "8388608" in script, "8 GiB checkout bound disappeared"
    assert "*/_work/*/*)" in script, "workspace-shape safety check disappeared"
    assert '[ "$PWD" = "$GITHUB_WORKSPACE" ]' in script
    assert 'mv .git "$CHECKOUT_TRASH"' in script
    assert (
        script.index('mv .git "$CHECKOUT_TRASH"')
        < script.index('find "$GITHUB_WORKSPACE"')
    ), "the Git store must be quarantined before the disposable tree is removed"


def test_render_checkout_uses_a_shallow_blobless_partial_clone():
    checkout = next(
        step for step in _steps() if step.get("uses") == "actions/checkout@v4"
    )
    assert checkout["with"]["ref"] == "main"
    assert checkout["with"]["filter"] == "blob:none"
    assert checkout["with"]["fetch-depth"] == 1
    assert "sparse-checkout" not in checkout["with"], (
        "render builders require the complete current data/ and site/ tree"
    )


def test_quarantine_cleanup_is_exact_and_runs_even_after_failure():
    cleanup = next(
        step
        for step in _steps()
        if step.get("name") == "remove oversized-checkout quarantine"
    )
    assert "always()" in cleanup["if"]
    script = cleanup["run"]
    assert '"${RUNNER_TEMP:?}"/macro-git-' in script
    assert 'rm -rf -- "$CHECKOUT_TRASH"' in script
