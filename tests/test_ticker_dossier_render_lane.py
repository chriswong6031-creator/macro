"""Release-lane contract for the Company Intelligence ticker shell."""

from __future__ import annotations

from pathlib import Path

import yaml


from scripts.workflow_run_source import resolved_workflow_text

ROOT = Path(__file__).resolve().parents[1]
RENDER_PATH = ROOT / ".github" / "workflows" / "render.yml"
ENGINE_RENDER_PATH = ROOT / ".github" / "workflows" / "engine-render.yml"
DAILY_PATH = ROOT / ".github" / "workflows" / "daily.yml"


def _steps(path: Path) -> list[dict]:
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    job = next(iter((workflow.get("jobs") or {}).values()))
    return [step for step in job.get("steps", []) if isinstance(step, dict)]


def _named_step(path: Path, name: str) -> tuple[int, dict, list[dict]]:
    steps = _steps(path)
    for index, step in enumerate(steps):
        if step.get("name") == name:
            return index, step, steps
    raise AssertionError(f"{path.name} is missing step {name!r}")


def test_render_lane_builds_and_guards_ticker_dossiers_before_global_guards():
    index, step, steps = _named_step(
        RENDER_PATH, "render ticker dossiers from rebuilt US stockdata"
    )
    names = [item.get("name") for item in steps]
    assert names.index("re-render pages from committed data (resilient; no collect / no LLM / no EDGAR)") < index
    assert index < names.index("ensure node for the inline-JS guard")
    assert step.get("env", {}).get("RENDER_NO_DRIP") == "1"
    run = step["run"]
    assert "set -euo pipefail" in run
    assert "steps.pick.outputs.scope" in run
    assert "*+all+*|*+macro+*" in run
    assert "python -m scripts.build_ticker_pages" in run
    assert '--manifest-out "$MANIFEST"' in run
    assert 'python - "$MANIFEST" "$COUNT"' in run
    assert "ticker-page-render-manifest.v1" in run
    assert 'manifest.get("failure_count")' in run
    assert 'manifest.get("index_written") is not True' in run
    assert "ticker_pages::rendered=" in run
    assert "data-company-intelligence" in run
    assert "company-intelligence-dossier.js" in run


def test_render_lane_guards_dossier_integrity_after_ticker_build():
    """The machine-sentinel estate guard (scripts/check_stock_dossier_integrity.py)
    must run immediately after the ticker dossiers are (re)built and before the
    unrelated global site guards — a NaN/Infinity leak into a rendered page is a
    per-page defect the render manifest's failure_count check cannot see."""
    build_index, _build_step, steps = _named_step(
        RENDER_PATH, "render ticker dossiers from rebuilt US stockdata"
    )
    guard_index, guard_step, _ = _named_step(
        RENDER_PATH, "guard — stock dossier integrity (sentinel + identity)"
    )
    names = [item.get("name") for item in steps]
    assert build_index < guard_index < names.index("ensure node for the inline-JS guard")
    assert "check_stock_dossier_integrity.py" in guard_step["run"]


def test_engine_lane_builds_dossiers_for_all_or_macro_but_not_fast():
    index, step, steps = _named_step(
        ENGINE_RENDER_PATH, "render ticker dossiers from rebuilt US stockdata"
    )
    names = [item.get("name") for item in steps]
    assert names.index("re-render pages from the freshly recomputed engine output (resilient)") < index
    assert index < names.index("ensure node for the inline-JS guard")
    assert step.get("env", {}).get("RENDER_NO_DRIP") == "1"
    run = step["run"]
    assert "set -euo pipefail" in run
    assert "all|macro)" in run
    assert "fast)" not in run
    assert "python -m scripts.build_ticker_pages" in run
    assert '--manifest-out "$MANIFEST"' in run
    assert 'python - "$MANIFEST" "$COUNT"' in run
    assert "ticker-page-render-manifest.v1" in run
    assert 'manifest.get("failure_count")' in run
    assert 'manifest.get("index_written") is not True' in run
    assert "ticker_pages::rendered=" in run
    assert "data-company-intelligence" in run
    assert "company-intelligence-dossier.js" in run


def test_ticker_builder_is_owned_and_narrowed_to_macro():
    render = RENDER_PATH.read_text(encoding="utf-8")
    assert '- "scripts/build_ticker_pages.py"' in render
    macro_arm = next(
        line
        for line in render.splitlines()
        if "templates/dashboard.html.j2" in line and "echo macro" in line
    )
    for path in (
        "templates/ticker.html.j2",
        "templates/ticker_index.html.j2",
        "scripts/build_ticker_pages.py",
    ):
        assert path in macro_arm


def test_nightly_order_remains_build_site_then_ticker_pages():
    # Resolved: both builders live in a body extracted to scripts/ci/, and
    # this assertion is positional — see scripts/workflow_run_source.
    daily = resolved_workflow_text(DAILY_PATH, ROOT)
    assert daily.index("scripts.build_site") < daily.index("scripts.build_ticker_pages")


def test_engine_render_lane_also_guards_dossier_integrity():
    """engine-render.yml rebuilds the SAME public dossier estate, so it inherits the
    same release standard. Guarding only render.yml would leave a lane that can
    publish a wrong-company page through a green run."""
    index, step, steps = _named_step(
        ENGINE_RENDER_PATH, "guard — stock dossier integrity (sentinel + identity)"
    )
    names = [item.get("name") for item in steps]
    assert names.index("render ticker dossiers from rebuilt US stockdata") < index
    assert "check_stock_dossier_integrity.py" in step["run"]
