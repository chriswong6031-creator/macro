"""Release-lane contract for the Company Intelligence ticker shell."""

from __future__ import annotations

from pathlib import Path

import yaml


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
    daily = DAILY_PATH.read_text(encoding="utf-8")
    assert daily.index("scripts.build_site") < daily.index("scripts.build_ticker_pages")
