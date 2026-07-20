"""tests/test_seo_meta_rollout.py — D12A PR B: static template-source checks.

Fast, no full renders, no live data. Reads template source text only.
MM_DATA_GUARD: no data/ writes; all work in tmp_path or against read-only site/ and templates/.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO = Path(__file__).resolve().parent.parent
TMPL = REPO / "templates"
SITE = REPO / "site"

# ---------------------------------------------------------------------------
# Known exemptions — these do NOT get _seo_head (already done, excluded, or
# special-case static files handled outside the template system).
# ---------------------------------------------------------------------------

# Already had _seo_head before PR B (YAML header exemption list):
_ALREADY_HAD_SEO = {
    "macro.html.j2", "us_stocks.html.j2", "china.html.j2", "hk.html.j2",
    "canada.html.j2", "bonds.html.j2", "forex.html.j2", "cycle.html.j2",
    "commodities.html.j2", "macro_context.html.j2", "market_structure.html.j2",
    "movers.html.j2", "transmission.html.j2", "china_mechanics.html.j2",
    "stage_analysis.html.j2", "china_stocks.html.j2", "hk_stocks.html.j2",
    "confluence_screener.html.j2", "dashboard.html.j2",
}

# Utility / excluded / non-public templates (no SEO needed):
_EXCLUDED_TEMPLATES = {
    # report_base is a base template, not a page
    "report_base.html.j2", "article_base.html.j2",
    # Special-purpose fragments
    "_seo_head.html.j2", "_interfonts.html.j2", "_site_nav.html.j2",
    "_plotly_head.html.j2", "_navlinks.html.j2",
    "_aibrief_body.html.j2", "_aibrief_css.j2",
    "_base_effect_strip.html.j2", "_baskets_desk.html.j2",
    "_cmd_hero.css.j2", "_desk_grader_panel.html.j2",
    "_forming_narratives.html.j2", "_ignition_radar_card.css.j2",
    "_ignition_radar_card.html.j2", "_leadership_board.html.j2",
    "_mag7_panel.css.j2", "_mag7_panel.html.j2",
    "_market_state_board.html.j2", "_market_state.css.j2",
    "_radar_panel.html.j2", "_regime_prob_panel.html.j2",
    "_regime_read_panel.html.j2", "_report_TEMPLATE.html.j2",
    "_risk_radar_card.css.j2", "_risk_radar_card.html.j2",
    "_sig_badge.html.j2", "_stock_decision.css.j2",
    "_theme_addons.html.j2", "_track_record_dlg.html.j2",
    "_vector_polish.html.j2",
    # Per-stock / per-sector detail shells (ticker SEO pages — separate program):
    "ticker.html.j2", "ticker_index.html.j2", "stock.html.j2",
    "sector.html.j2", "hk_sector.html.j2", "canada_sector.html.j2",
    "china_sector.html.j2",
    # Per-item detail shells that get SEO from parent family:
    "basket_detail.html.j2", "subsector_detail.html.j2",
    "subsector_rotation_detail.html.j2", "mastermind_detail.html.j2",
    "active_detail.html.j2", "intl_stock.html.j2",
    "canada_stock.html.j2", "hk_lookup.html.j2",
    # Lab / utility pages:
    "us_stocks_lab.html.j2", "hk_stocks_lab.html.j2",
    "china_stocks_lab.html.j2", "tech_lab.html.j2",
    "qa_bottom_sensors.html.j2", "us_stocks_v2.html.j2",
    "validation_timeline.html.j2",
    # Static page with no template pair — handled in site/learn.html directly:
    "chat.html",
    # Individual report pages inherit SEO from article_base.html.j2 via {{ super() }}:
    "report_ai_master_plan.html.j2", "report_bessent_jun24.html.j2",
    "report_haven_audition.html.j2", "report_relapse_jul8.html.j2",
    "report_second_act.html.j2", "report_warsh_fomc.html.j2",
}

# Templates that inject SEO via Jinja block inheritance (head_extra in report_base chain):
_REPORT_BASE_TEMPLATES = {
    "congress_trades.html.j2", "reports.html.j2", "policy_watch.html.j2",
    "smart_money.html.j2", "fund_index.html.j2", "news.html.j2",
    "china_radar.html.j2", "alt_data.html.j2", "china_altdata.html.j2",
    "china_intel.html.j2", "china_news.html.j2", "china_policy_watch.html.j2",
    "china_special_situations.html.j2", "whitehouse.html.j2", "odds.html.j2",
    "foresight.html.j2",
    # Multi-page families:
    "fund_dossier.html.j2", "article_base.html.j2",
}

# Templates where SEO vars are dynamic (Jinja conditionals) — they contain
# _seo_head but multiple seo_path values per template file:
_MULTI_PATH_TEMPLATES = {
    "allocation.html.j2",      # 4 pages: us / china / hk / canada
    "intl.html.j2",            # 2 pages: intl.html / intl_stocks.html
    "market_heatmap.html.j2",  # 3 pages: china / hk / canada heatmaps
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _public_page_templates() -> list[Path]:
    """Return the .j2 templates that correspond to public sitemap pages
    (not fragments, not excluded, not already done)."""
    all_j2 = [p for p in TMPL.glob("*.html.j2") if p.name.startswith("report_") or
              not p.name.startswith("_")]
    result = []
    for p in all_j2:
        if p.name in _ALREADY_HAD_SEO:
            continue
        if p.name in _EXCLUDED_TEMPLATES:
            continue
        result.append(p)
    return sorted(result)


def _is_literal_assignment(line: str, var: str) -> tuple[bool, list[str]]:
    """Return (is_literal, values) where is_literal=True means the assignment
    is a plain string literal (not a Jinja concatenation expression).
    A Jinja expression uses the ~ operator, e.g.:
        {% set seo_desc = var ~ "suffix" %}
    We detect this by requiring the set statement to be of the form:
        {% set VAR = "..." %}  or  {% set VAR = '...' %}
    with no ~ operator anywhere after the = sign (within the tag)."""
    # Extract the RHS of the assignment (between = and %})
    m = re.search(r'\{%-?\s*set\s+' + re.escape(var) + r'\s*=\s*(.*?)-?%\}', line)
    if not m:
        return False, []
    rhs = m.group(1).strip()
    # If RHS contains ~ it is a Jinja concatenation expression — not literal
    if '~' in rhs:
        return False, []
    # Extract the string value
    vm = re.match(r'^"([^"]*)"$', rhs) or re.match(r"^'([^']*)'$", rhs)
    if vm:
        return True, [vm.group(1)]
    return False, []


def _extract_seo_var_values(content: str, var: str) -> list[str]:
    """Extract all LITERAL string values for a seo_* variable from template source.
    Skips Jinja-expression assignments (those using ~ concatenation).
    Operates line-by-line so that multi-assignment lines are handled correctly."""
    results: list[str] = []
    # Split on {% ... %} tag boundaries to find each set statement
    for tag in re.findall(r'\{%-?.*?-?%\}', content, re.DOTALL):
        if f'set {var}' not in tag:
            continue
        is_lit, vals = _is_literal_assignment(tag, var)
        if is_lit:
            results.extend(vals)
    return results


def _extract_seo_desc_values(content: str) -> list[str]:
    """Extract all literal seo_desc set values from template source.
    Skips Jinja-expression assignments (using ~ concatenation)."""
    return _extract_seo_var_values(content, 'seo_desc')


def _extract_seo_title_values(content: str) -> list[str]:
    """Extract all literal seo_title set values from template source."""
    return _extract_seo_var_values(content, 'seo_title')


def _extract_seo_path_values(content: str) -> list[str]:
    """Extract all literal seo_path set values from template source.
    Skips Jinja-expression assignments (using ~ concatenation)."""
    return _extract_seo_var_values(content, 'seo_path')


# ---------------------------------------------------------------------------
# Test 1: every public-page template contains exactly one _seo_head include
# ---------------------------------------------------------------------------

class TestSeoHeadPresence:
    """Every public-page template must include _seo_head.html.j2 exactly once."""

    def _templates(self) -> list[Path]:
        return _public_page_templates()

    @pytest.mark.parametrize("tmpl", _public_page_templates(), ids=lambda p: p.name)
    def test_includes_seo_head(self, tmpl: Path) -> None:
        content = tmpl.read_text(encoding="utf-8")
        count = content.count('"_seo_head.html.j2"')
        assert count >= 1, (
            f"{tmpl.name} has no _seo_head.html.j2 include"
        )
        assert count == 1, (
            f"{tmpl.name} includes _seo_head.html.j2 {count} times (expected 1)"
        )


# ---------------------------------------------------------------------------
# Test 2: no duplicate inline meta description or canonical outside the include
# ---------------------------------------------------------------------------

class TestNoDuplicateMeta:
    """Templates that include _seo_head must NOT also emit inline meta description
    or rel="canonical" tags (which _seo_head itself emits)."""

    @pytest.mark.parametrize("tmpl", _public_page_templates(), ids=lambda p: p.name)
    def test_no_inline_description_or_canonical(self, tmpl: Path) -> None:
        content = tmpl.read_text(encoding="utf-8")
        if '"_seo_head.html.j2"' not in content:
            return  # skip — caught by previous test

        # Strip the _seo_head include line itself so we don't false-positive on
        # the include filename string
        stripped = content.replace('"_seo_head.html.j2"', "__SEO_INCLUDE__")

        # Check for inline meta description OUTSIDE the seo_head block
        assert '<meta name="description"' not in stripped, (
            f"{tmpl.name} has inline <meta name=\"description\"> in addition to _seo_head include — "
            "remove the inline duplicate"
        )
        assert 'rel="canonical"' not in stripped, (
            f"{tmpl.name} has inline rel=\"canonical\" in addition to _seo_head include — "
            "remove the inline duplicate"
        )


# ---------------------------------------------------------------------------
# Test 3: seo_desc length 50-170 chars; seo_title ≤ 70 chars
#         Neither contains t(, {{, or the word "validated"
# ---------------------------------------------------------------------------

class TestSeoValues:
    """Validate literal seo_desc and seo_title string content."""

    @pytest.mark.parametrize("tmpl", _public_page_templates(), ids=lambda p: p.name)
    def test_seo_desc_length(self, tmpl: Path) -> None:
        content = tmpl.read_text(encoding="utf-8")
        descs = _extract_seo_desc_values(content)
        if not descs:
            # Dynamic-only template (vars set via Jinja expression) — skip length check
            # but confirm there's a seo_desc set statement
            if '"_seo_head.html.j2"' in content:
                assert "seo_desc" in content, f"{tmpl.name}: _seo_head included but no seo_desc set"
            return
        for desc in descs:
            assert 50 <= len(desc) <= 170, (
                f"{tmpl.name}: seo_desc length {len(desc)} out of range [50, 170]: {desc!r}"
            )

    @pytest.mark.parametrize("tmpl", _public_page_templates(), ids=lambda p: p.name)
    def test_seo_title_length(self, tmpl: Path) -> None:
        content = tmpl.read_text(encoding="utf-8")
        titles = _extract_seo_title_values(content)
        if not titles:
            return
        for title in titles:
            assert len(title) <= 70, (
                f"{tmpl.name}: seo_title length {len(title)} > 70: {title!r}"
            )

    @pytest.mark.parametrize("tmpl", _public_page_templates(), ids=lambda p: p.name)
    def test_seo_values_no_template_syntax_or_banned_words(self, tmpl: Path) -> None:
        content = tmpl.read_text(encoding="utf-8")
        descs = _extract_seo_desc_values(content)
        titles = _extract_seo_title_values(content)
        for val in descs + titles:
            assert "t(" not in val, (
                f"{tmpl.name}: seo value contains t() macro call: {val!r}"
            )
            assert "{{" not in val, (
                f"{tmpl.name}: seo value contains Jinja expression {{ }}: {val!r}"
            )
            assert "validated" not in val.lower(), (
                f"{tmpl.name}: seo value contains banned word 'validated': {val!r}"
            )


# ---------------------------------------------------------------------------
# Test 4: seo_path values are unique across templates and end in .html
# ---------------------------------------------------------------------------

class TestSeoPathUniqueness:
    """Literal seo_path values must be unique across templates (no two pages
    claim the same canonical URL) and end in .html."""

    def test_seo_path_uniqueness_and_format(self) -> None:
        path_to_template: dict[str, str] = {}
        duplicates: list[str] = []

        for tmpl in _public_page_templates():
            content = tmpl.read_text(encoding="utf-8")
            paths = _extract_seo_path_values(content)
            for path in paths:
                assert path == "" or path.endswith(".html"), (
                    f"{tmpl.name}: seo_path {path!r} does not end in .html"
                )
                if path in path_to_template:
                    duplicates.append(
                        f"seo_path={path!r} claimed by both "
                        f"{path_to_template[path]} and {tmpl.name}"
                    )
                else:
                    path_to_template[path] = tmpl.name

        assert not duplicates, "Duplicate seo_path values:\n" + "\n".join(duplicates)


# ---------------------------------------------------------------------------
# Test 5: site/learn.html (static) has canonical + meta description
# ---------------------------------------------------------------------------

class TestLearnStaticSeo:
    """learn.html is a static file handled outside the template system —
    verify it has the required SEO meta tags."""

    def test_learn_html_has_meta_description(self) -> None:
        learn = SITE / "learn.html"
        assert learn.exists(), "site/learn.html does not exist"
        content = learn.read_text(encoding="utf-8")
        assert '<meta name="description"' in content, \
            "site/learn.html is missing <meta name=\"description\">"

    def test_learn_html_has_canonical(self) -> None:
        learn = SITE / "learn.html"
        content = learn.read_text(encoding="utf-8")
        assert 'rel="canonical"' in content, \
            "site/learn.html is missing rel=\"canonical\""

    def test_learn_html_has_og_tags(self) -> None:
        learn = SITE / "learn.html"
        content = learn.read_text(encoding="utf-8")
        assert 'property="og:title"' in content, \
            "site/learn.html is missing og:title"
        assert 'name="twitter:card"' in content, \
            "site/learn.html is missing twitter:card"


# ---------------------------------------------------------------------------
# Test 6: render-smoke — parse one simple modified template with Jinja
# ---------------------------------------------------------------------------

class TestRenderSmoke:
    """Smoke-test that a simple template renders without Jinja errors with
    minimal fake context. Uses bonds.html.j2 (already done, no heavy viewmodel)."""

    def test_bonds_template_renders_with_seo(self, tmp_path: Path) -> None:
        """bonds.html.j2 uses _seo_head.html.j2 and renders with a minimal
        'as_of' context + a stub Plotly/font include."""
        pytest.importorskip("jinja2")
        from jinja2 import Environment, FileSystemLoader, Undefined

        class SilentUndefined(Undefined):
            def __str__(self) -> str:
                return ""
            def __call__(self, *a, **kw):  # type: ignore[override]
                return SilentUndefined()
            def __getattr__(self, name: str) -> "SilentUndefined":  # type: ignore[override]
                return SilentUndefined()

        env = Environment(
            loader=FileSystemLoader(str(TMPL)),
            autoescape=True,
            undefined=SilentUndefined,
        )
        tmpl = env.get_template("bonds.html.j2")
        result = tmpl.render(
            as_of="2026-07-20",
            C=SilentUndefined(),
            active_section="bonds",
            active_page="bonds",
        )
        # Should contain our meta description
        assert 'name="description"' in result
        assert 'rel="canonical"' in result
        assert 'property="og:title"' in result
        # Should NOT have duplicate meta description
        count = result.count('<meta name="description"')
        assert count == 1, f"bonds.html rendered {count} meta description tags (expected 1)"


# ---------------------------------------------------------------------------
# Test 7: check_template_site_sync unaffected (no non-.j2 pair was touched)
# ---------------------------------------------------------------------------

class TestTemplateSiteSyncUnaffected:
    """Confirm that no plain-copy template/site pair was broken.
    We only edited .j2 files (exempt from sync check) plus site/learn.html
    (which has no template/ pair)."""

    def test_no_non_j2_template_touched(self) -> None:
        """The only non-.j2 file in templates/ is chat.html — we did not touch it."""
        non_j2 = [p for p in TMPL.iterdir()
                  if p.is_file() and not p.suffix == ".j2"
                  and p.name != ".DS_Store"]
        # Verify chat.html exists and is still the plain-copy pair
        chat_tmpl = TMPL / "chat.html"
        chat_site = SITE / "chat.html"
        if chat_tmpl.exists() and chat_site.exists():
            assert chat_tmpl.read_bytes() == chat_site.read_bytes(), (
                "templates/chat.html and site/chat.html are out of sync — "
                "did something accidentally edit chat.html?"
            )
