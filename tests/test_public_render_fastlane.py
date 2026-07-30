from __future__ import annotations

import re
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
        "!templates/_public_chrome_css.html.j2",
        "!templates/_public_chrome_js.html.j2",
        "!templates/_public_footer.html.j2",
        "!templates/_public_nav.html.j2",
        "!templates/plans.html.j2",
        "!templates/seo_base.html.j2",
        "!templates/support.html.j2",
        "!templates/unsubscribe.html.j2",
    ):
        assert f'- "{pattern}"' in HEAVY
    assert '"scripts/build_public_pages.py"' not in HEAVY, (
        "the heavy lane's positive builder allowlist must leave the public builder "
        "exclusively to public-render"
    )


def test_public_render_owns_the_excluded_surfaces():
    for pattern in (
        "templates/*.html",
        "templates/*.css",
        "templates/*.js",
        "templates/_public_chrome_css.html.j2",
        "templates/_public_chrome_js.html.j2",
        "templates/_public_footer.html.j2",
        "templates/_public_nav.html.j2",
        "templates/plans.html.j2",
        "templates/seo_base.html.j2",
        "templates/support.html.j2",
        "templates/unsubscribe.html.j2",
        "scripts/build_public_pages.py",
        "config/plans.yml",
    ):
        assert f'- "{pattern}"' in PUBLIC
    assert "runs-on: ubuntu-latest" in PUBLIC
    assert "timeout-minutes: 20" in PUBLIC
    assert "cancel-in-progress: true" in PUBLIC
    assert "fetch-depth: 2" in PUBLIC
    assert "fetch-depth: 0" not in PUBLIC


def test_public_render_never_invokes_market_or_data_builders():
    assert "scripts.build_site" not in PUBLIC_SH
    assert "scripts.build_canada" not in PUBLIC_SH
    assert "scripts.build_intl" not in PUBLIC_SH
    assert "fetch_r2" not in PUBLIC_SH
    assert "publish_r2" not in PUBLIC_SH
    assert "read_parquet" not in PUBLIC_SH


def test_public_render_retry_does_not_repeat_the_full_site_js_guard():
    """Busy-main retries must stay shorter than the repository's merge cadence.

    Run 30505255868 spent ~2m30s re-validating all 3,263 pages after each
    successful rebase, lost the ref again, and exhausted its push budget.
    """
    assert "check_inline_js.py site\n" not in PUBLIC_SH
    assert 'PUBLIC_OUTPUTS=(site/plans.html site/support.html site/unsubscribe.html)' in PUBLIC_SH
    assert 'check_inline_js.py "${PUBLIC_OUTPUTS[@]}"' in PUBLIC_SH
    assert 'if [ "$(git rev-parse HEAD)" != "$PRE_SYNC_HEAD" ]; then' in PUBLIC_SH
    assert "PUSH_BUDGET_SECS=600" in PUBLIC_SH


def test_public_builder_renders_current_pricing_without_market_data(tmp_path):
    build_public_pages.build(tmp_path)

    plans = (tmp_path / "plans.html").read_text()
    assert 'data-m-pm="99" data-a-pm="75"' in plans
    assert 'data-m-pm="149" data-a-pm="109"' in plans
    assert "Founding Pro" in plans
    assert "$900 a year" in plans
    # Founding copy is availability-framed (#3856): the cap is real enforced
    # inventory, never a fabricated "signed up/claimed" count.
    assert 'data-offer-cap="2000"' in plans
    assert "2,000 total" in plans
    assert "first come, first served" in plans
    assert "The allotment shrinks daily" in plans
    assert 'aria-label="Founding Pro memberships no longer available"' in plans
    assert "signed up" not in plans
    assert (tmp_path / "support.html").is_file()
    assert (tmp_path / "unsubscribe.html").is_file()


def test_public_pages_do_not_double_escape_entities(tmp_path):
    """An HTML entity written inside a t() string gets escaped a second time.

    The builder renders with autoescape ON, so a source "&amp;" reaches the
    reader as "&amp;amp;" — literally "&amp;" on the page. This shipped twice:
    the shared footer link read "Plans &amp; pricing" on every public page, and
    two feature tips on plans.html read "options &amp; flow" / "M&amp;A". Write
    a bare "&" in the Jinja string and let autoescape do its job.
    """
    build_public_pages.build(tmp_path)

    offenders = {
        page.name: sorted({m for m in re.findall(r"&amp;(?:amp|lt|gt|quot|#\d+);", page.read_text())})
        for page in sorted(tmp_path.glob("*.html"))
    }
    offenders = {name: hits for name, hits in offenders.items() if hits}
    assert not offenders, f"double-escaped entities reach the reader: {offenders}"
