"""BioCatalyst's public shell, client boundary, and build integration tests."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from scripts.build_biocatalyst import render_from_state


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"


def _render() -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=True,
        undefined=StrictUndefined,
    )
    return env.get_template("biocatalyst.html.j2").render(
        generated_utc="2026-08-02T12:00:00Z",
        active_section="research",
        active_page="biocatalyst",
    )


def test_biocatalyst_shell_is_bilingual_shared_navigation_only_and_data_free():
    source = (TEMPLATES / "biocatalyst.html.j2").read_text(encoding="utf-8")
    html = _render()

    assert source.count('{% include "_site_nav.html.j2" %}') == 1
    assert "<nav" not in source
    assert html.count('class="site-nav"') == 1
    assert html.count('class="l-en"') >= 20
    assert html.count('class="l-zh"') >= 20
    assert "Clinical Trial Watch" in html
    assert "临床试验观察" in html

    # The static shell explains the product but cannot disclose a study, a
    # generated list, or an opaque internal record reference before site_full
    # has been enforced by the API.
    assert re.search(r"\bNCT\d{8}\b", html) is None
    for forbidden in (
        '"trials"',
        '"nct_id"',
        "canonical_study",
        "source_snapshot",
        "generation_id",
        "raw_object_key",
    ):
        assert forbidden not in html


def test_biocatalyst_shell_has_one_accessible_three_pane_workbench():
    html = _render()
    for identifier in (
        "bci-filter-pane",
        "bci-queue-pane",
        "bci-inspector-pane",
        "bci-search",
        "bci-phase-filter",
        "bci-status-filter",
        "bci-condition-filter",
        "bci-queue",
        "bci-inspector-body",
        "bci-refresh",
    ):
        assert f'id="{identifier}"' in html or f'class="{identifier}"' in html
    ids = re.findall(r'\bid="([^"]+)"', html)
    assert len(ids) == len(set(ids))
    assert "This view does not make a forecast or a trade call." in html
    assert "<option" in html
    assert re.search(r"<option[^>]*>\s*<span", html) is None


def test_biocatalyst_client_uses_only_the_authenticated_fact_api():
    js = (TEMPLATES / "biocatalyst.js").read_text(encoding="utf-8")
    for token in (
        "/api/biocatalyst/v1/trials",
        "headers.Authorization = 'Bearer ' + token",
        "window.MDXAuth.client",
        "credentials: 'same-origin'",
        "cache: 'no-store'",
        "textContent",
        "encodeURIComponent(id)",
        "rel = 'noopener noreferrer'",
        "URLSearchParams",
        "aria-selected",
        "ArrowDown",
        "Escape",
        "langchange",
        "Primary endpoints",
        "Secondary endpoints",
        "bci-endpoint",
        "next_cursor",
        "?limit=250",
        "sameGeneration",
        "Repeated trial pagination cursor",
    ):
        assert token in js
    assert "innerHTML" not in js
    assert "clinicaltrials.gov/study/" in js
    assert "probability" not in js.lower()


def test_biocatalyst_assets_have_responsive_motion_and_focus_guards():
    css = (TEMPLATES / "biocatalyst.css").read_text(encoding="utf-8")
    for token in (
        "@media (min-width: 1121px)",
        "@media (max-width: 1120px)",
        "@media (max-width: 760px)",
        ":focus-visible",
        "prefers-reduced-motion",
        ".bci-inspector-pane.is-open",
        ".bci-scrim",
        ".bci-inspector-close,.bci-scrim { display: none !important; }",
        "backdrop-filter: none",
        "min-height: 0; height: 100%; overflow: hidden",
    ):
        assert token in css


def test_biocatalyst_renderer_writes_only_the_shell_and_paired_assets(tmp_path: Path):
    # The builder must be testable without mutating the repository's served
    # tree. It only needs the template family, so a directory symlink preserves
    # the real include graph while redirecting all emitted site bytes.
    (tmp_path / "templates").symlink_to(TEMPLATES, target_is_directory=True)
    page = render_from_state(tmp_path)
    html = page.read_text(encoding="utf-8")
    assert page == tmp_path / "site" / "biocatalyst.html"
    assert re.search(r"\bNCT\d{8}\b", html) is None
    assert (tmp_path / "site" / "biocatalyst.css").read_bytes() == (TEMPLATES / "biocatalyst.css").read_bytes()
    assert (tmp_path / "site" / "biocatalyst.js").read_bytes() == (TEMPLATES / "biocatalyst.js").read_bytes()
    assert not list((tmp_path / "site").glob(".biocatalyst.*.tmp"))
    assert 'src="biocatalyst.js"' in html
    assert 'href="biocatalyst.css"' in html


def test_biocatalyst_is_registered_preview_with_a_site_full_api_boundary():
    policy = yaml.safe_load((ROOT / "config" / "site_access.yml").read_text(encoding="utf-8"))
    free_registered = policy["free_registered"]["exact"]
    assert "/biocatalyst.html" in free_registered
    assert "/biocatalyst.css" in free_registered
    assert "/biocatalyst.js" in free_registered

    page_source = (TEMPLATES / "biocatalyst.html.j2").read_text(encoding="utf-8")
    api_source = (ROOT / "app" / "biocatalyst.py").read_text(encoding="utf-8")
    assert "/api/biocatalyst/" not in page_source
    assert "require_site_full_user" in api_source
    assert "enforce_site_full" in api_source


def test_biocatalyst_is_wired_into_the_site_renderer_and_research_navigation():
    site_builder = (ROOT / "scripts" / "build_site.py").read_text(encoding="utf-8")
    nav = (TEMPLATES / "_navlinks.html.j2").read_text(encoding="utf-8")
    plans = (TEMPLATES / "plans.html.j2").read_text(encoding="utf-8")
    assert "scripts.build_biocatalyst" in site_builder
    assert "biocatalyst.html render failed" in site_builder
    assert nav.count("biocatalyst.html") == 1
    assert "BioCatalyst Intelligence" in nav
    assert plans.count("BioCatalyst Trial Watch") == 2
    assert "probability" not in plans.lower()
    assert "forecast" in plans.lower()  # explicit non-forecast boundary


def test_render_lane_owns_and_narrows_biocatalyst_builder():
    render = (ROOT / ".github" / "workflows" / "render.yml").read_text(
        encoding="utf-8"
    )
    assert '- "scripts/build_biocatalyst.py"' in render
    assert "templates/biocatalyst.*" in render
    assert "scripts/build_biocatalyst.py) echo macro;;" in render


def test_biocatalyst_runtime_is_valid_javascript():
    node = shutil.which("node")
    if node is None:
        return
    result = subprocess.run(
        [node, "--check", str(TEMPLATES / "biocatalyst.js")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
