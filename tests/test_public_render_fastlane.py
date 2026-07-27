from __future__ import annotations

from pathlib import Path

import yaml

from scripts import build_public_pages

ROOT = Path(__file__).resolve().parents[1]
HEAVY = (ROOT / ".github" / "workflows" / "render.yml").read_text()
PUBLIC = (ROOT / ".github" / "workflows" / "public-render.yml").read_text()
PUBLIC_SH = (ROOT / "scripts" / "ci" / "public_render.sh").read_text()


def test_no_workflow_run_expression_can_hit_githubs_21000_character_limit():
    """GitHub rejects the whole workflow before creating a job at 21,000 chars."""
    offenders = []
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        parsed = yaml.safe_load(path.read_text()) or {}
        for job_name, job in (parsed.get("jobs") or {}).items():
            for index, step in enumerate(job.get("steps") or []):
                run = step.get("run") if isinstance(step, dict) else None
                if isinstance(run, str) and len(run) > 20_500:
                    offenders.append((path.name, job_name, index, len(run)))
    assert not offenders, (
        "GitHub hard-fails run expressions above 21,000 characters; "
        f"split or trim these blocks: {offenders}"
    )


def test_heavy_render_excludes_public_surfaces():
    for pattern in (
        "!templates/*.html",
        "!templates/*.css",
        "!templates/*.js",
        "!templates/plans.html.j2",
        "!templates/support.html.j2",
        "!templates/unsubscribe.html.j2",
        "!scripts/build_public_pages.py",
    ):
        assert f'- "{pattern}"' in HEAVY


def test_public_render_owns_the_excluded_surfaces():
    for pattern in (
        "templates/*.html",
        "templates/*.css",
        "templates/*.js",
        "templates/plans.html.j2",
        "templates/support.html.j2",
        "templates/unsubscribe.html.j2",
        "scripts/build_public_pages.py",
        "config/plans.yml",
    ):
        assert f'- "{pattern}"' in PUBLIC
    assert "runs-on: ubuntu-latest" in PUBLIC
    assert "cancel-in-progress: true" in PUBLIC


def test_public_render_never_invokes_market_or_data_builders():
    assert "scripts.build_site" not in PUBLIC_SH
    assert "scripts.build_canada" not in PUBLIC_SH
    assert "scripts.build_intl" not in PUBLIC_SH
    assert "fetch_r2" not in PUBLIC_SH
    assert "publish_r2" not in PUBLIC_SH
    assert "read_parquet" not in PUBLIC_SH


def test_public_builder_renders_current_pricing_without_market_data(tmp_path):
    build_public_pages.build(tmp_path)

    plans = (tmp_path / "plans.html").read_text()
    assert 'data-m-pm="99" data-a-pm="75"' in plans
    assert 'data-m-pm="149" data-a-pm="109"' in plans
    assert "Founding Pro" in plans
    assert "$900 a year" in plans
    assert "2,000 memberships" in plans
    assert (tmp_path / "support.html").is_file()
    assert (tmp_path / "unsubscribe.html").is_file()
